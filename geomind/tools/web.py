"""The tools that search the web and read one page, through the run's search service.

``web_search`` asks the SearXNG instance at the ``search_url`` setting (``GEOMIND_SEARCH_URL``)
for JSON results; ``read_web_page`` fetches one public page and returns its main text with the
title, publisher and date the page states. A run without ``search_url`` does not offer either
(``Session.missing_services``). A value from the web is a source to show the user, never a value
to use before the user approves it.

NOTE: ``read_web_page`` runs on the backend's network, so it refuses any address that is not
public (loopback, private, link-local, reserved) at every redirect: no page can reach the
services beside the backend. Only ``http`` and ``https``; HTML and PDF.
"""

import asyncio
import io
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from geomind import runtime
from geomind.context.skills import skill_hint
from geomind.errors import ToolError
from geomind.tools.base import tool

HINT = skill_hint("web-search")
SEARCH_SECONDS = 20.0
PAGE_SECONDS = 20.0
MAX_BYTES = 5_000_000
PAGE_CHARACTERS = 30_000
SNIPPET_CHARACTERS = 400
MAX_REDIRECTS = 5
MAX_RESULTS = 10
USER_AGENT = "geomind-web-reader/1.0"
LANGUAGE = "en"
"""The language of every search: the results and the queries are English (QA-071)."""
MAX_SEARCHES = 6
"""The searches one agent makes in one run: about two values at three refined queries each
(QA-087: 39 searches for one value). Then a labelled assumption or a named gap."""
MAX_WORDS = 8
"""The most words a query has: a query is a few technical terms, never a sentence."""
FOREIGN_WORDS = frozenset(
    "het een voor naar van gemiddelde langjarig temperatuur aanvoer vochtigheid warmte warmtenet "
    "ontwerptemperatuur kosten prijs normaal relatieve und fur für mit kosten preis temperatur "
    "durchschnitt pour avec prix moyenne og av til ikke pris gjennomsnitt varme fjernvarme".split()
)
"""Common words of the languages seen in queries (Dutch, German, French, Norwegian) that are no
English words: a query that holds one is refused, so the search stays English."""
ALLOWED_SIGNS = set("°²³µ€±·–—’")
"""Signs outside ASCII that an English technical query may hold (units, a dash)."""
SKIPPED_TAGS = {
    "script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form", "iframe",
    "template", "button", "select",
}
BLOCK_TAGS = {
    "p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article",
    "table", "ul", "ol", "dd", "dt", "blockquote", "pre",
}
PUBLISHER_META = ("og:site_name", "citation_publisher", "dc.publisher", "publisher", "application-name")
DATE_META = (
    "article:published_time", "citation_publication_date", "citation_date", "dc.date",
    "date", "pubdate", "publish-date", "article:modified_time",
)
AUTHOR_META = ("author", "citation_author", "dc.creator", "article:author")


def _error(name, message, path=None, code="invalid_input"):
    """Return a ``ToolError`` of a web tool that points at its skill."""
    return ToolError(f"{name}: {message}; {HINT}", code=code, path=path)


def search_url():
    """Return the search service's URL; an unset setting raises and names it."""
    url = runtime.get("search_url")
    if not url:
        raise _error("web_search", "GEOMIND_SEARCH_URL is unset, so the web is not searched",
                     code="not_allowed")
    return url.rstrip("/")


def _cut(text, limit):
    """Return text cut to ``limit`` characters."""
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else f"{text[:limit].rstrip()} ..."


def query_problem(query):
    """Return why a query is not a short English technical query, or ``None`` when it is."""
    words = query.split()
    if len(words) > MAX_WORDS:
        return f"the query has {len(words)} words; expected at most {MAX_WORDS} technical terms"
    if any(not char.isascii() and char not in ALLOWED_SIGNS and char.isalpha() for char in query):
        return "the query has letters that are not English; expected an English query"
    foreign = sorted({word.lower().strip(",.;:()") for word in words} & FOREIGN_WORDS)
    if foreign:
        return f"the query has words that are not English ({', '.join(foreign)}); expected English"
    return None


@tool(effect="external")
async def web_search(context, query: str, limit: int = 5):
    """Search the web in English; return results with title, url, snippet, engine and date.

    Skill `web-search`.
    """
    import httpx

    if not isinstance(query, str) or not query.strip():
        raise _error("web_search", "query is empty", "query")
    searched = context.session.__dict__.setdefault("web_searches", [])
    if len(searched) >= MAX_SEARCHES:
        raise _error(
            "web_search",
            f"this agent searched {len(searched)} times in this run; no more searches: for each "
            "value still without a source, propose one labelled engineering assumption with a "
            "one-line reason in the confirmation question, or name it as a gap",
            "query",
            code="not_allowed",
        )
    problem = query_problem(query.strip())
    if problem is not None:
        raise _error("web_search", f"query = {query.strip()!r}: {problem}", "query")
    if not 1 <= limit <= MAX_RESULTS:
        raise _error("web_search", f"limit = {limit}; expected 1 to {MAX_RESULTS}", "limit")
    url = f"{search_url()}/search"
    try:
        async with httpx.AsyncClient(timeout=SEARCH_SECONDS) as client:
            response = await client.get(url, params={"q": query.strip(), "format": "json", "language": LANGUAGE})
        response.raise_for_status()
        found = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise _error("web_search", f"the search service did not answer: {error}",
                     code="unavailable") from error
    results = []
    for item in found.get("results") or []:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        engines = item.get("engines") or ([item["engine"]] if item.get("engine") else [])
        results.append(
            {
                "title": _cut(item.get("title"), 300),
                "url": item["url"],
                "snippet": _cut(item.get("content"), SNIPPET_CHARACTERS),
                "engine": ", ".join(engines) or None,
                "date": item.get("publishedDate") or None,
            }
        )
        if len(results) == limit:
            break
    searched.append(query.strip())
    return {"query": query.strip(), "results": results, "searches_left": MAX_SEARCHES - len(searched)}


def _is_public(host):
    """Tell whether every address ``host`` resolves to is public."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        return False
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if not address.is_global or address.is_multicast:
            return False
    return bool(infos)


async def _checked(url):
    """Return ``url`` when it is http(s) to a public host; anything else raises."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise _error("read_web_page", f"url = {url!r}; expected an http or https URL", "url")
    if parts.username or parts.password:
        raise _error("read_web_page", "url holds a user name or password", "url")
    if not await asyncio.to_thread(_is_public, parts.hostname):
        raise _error("read_web_page", f"url = {url!r}; the host is not a public address", "url",
                     code="not_allowed")
    return url


async def _fetch(url):
    """Return ``(final url, content type, bytes)``, following public redirects only."""
    import httpx

    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5"}
    async with httpx.AsyncClient(timeout=PAGE_SECONDS, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await _checked(url)
            async with client.stream("GET", url, headers=headers) as response:
                if response.is_redirect and response.headers.get("location"):
                    url = urljoin(url, response.headers["location"])
                    continue
                if response.status_code >= 400:
                    raise _error("read_web_page", f"the page answered {response.status_code}",
                                 "url", code="unavailable")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        raise _error("read_web_page", "the page is larger than 5 MB", "url")
                kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
                return str(response.url), kind, bytes(body)
    raise _error("read_web_page", f"more than {MAX_REDIRECTS} redirects", "url")


class _Page(HTMLParser):
    """Collect the visible text, the title and the meta tags of an HTML page."""

    def __init__(self):
        """Start empty."""
        super().__init__(convert_charrefs=True)
        self.parts, self.title, self.meta, self._skip, self._in_title = [], "", {}, 0, False

    def handle_starttag(self, tag, attrs):
        """Track skipped blocks, the title and meta tags."""
        if tag in SKIPPED_TAGS:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            found = dict(attrs)
            key = (found.get("property") or found.get("name") or "").lower()
            if key and found.get("content") and key not in self.meta:
                self.meta[key] = found["content"].strip()
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        """Close a skipped block or the title."""
        if tag in SKIPPED_TAGS and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        """Keep text outside skipped blocks."""
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)

    def text(self):
        """Return the text with one blank line between blocks."""
        lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in "".join(self.parts).split("\n"))
        return "\n".join(line for line in lines if line)


def _first(meta, keys):
    """Return the first meta value of ``keys``, or ``None``."""
    return next((meta[key] for key in keys if meta.get(key)), None)


def _html(content, kind):
    """Return the fields of an HTML page."""
    charset = re.search(rb"charset=[\"']?([A-Za-z0-9_-]+)", content[:2048])
    try:
        text = content.decode(charset.group(1).decode() if charset else "utf-8", errors="replace")
    except LookupError:
        text = content.decode("utf-8", errors="replace")
    page = _Page()
    page.feed(text)
    meta = page.meta
    return {
        "title": _cut(meta.get("og:title") or meta.get("citation_title") or page.title, 300) or None,
        "publisher": _first(meta, PUBLISHER_META),
        "author": _first(meta, AUTHOR_META),
        "date": _first(meta, DATE_META),
        "text": page.text(),
    }


def _pdf(content):
    """Return the fields of a PDF: its metadata and the text of its pages."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(content))
        info = reader.metadata or {}
        pages = [f"[page {number}]\n{page.extract_text() or ''}" for number, page in
                 enumerate(reader.pages, start=1)]
    except Exception as error:  # pypdf raises many kinds on a broken file
        raise _error("read_web_page", f"the PDF could not be read: {error}", "url") from error
    return {
        "title": (info.get("/Title") or None),
        "publisher": None,
        "author": info.get("/Author") or None,
        "date": str(info.get("/CreationDate") or "") or None,
        "text": "\n".join(pages),
        "pages": len(pages),
    }


@tool(effect="external")
async def read_web_page(url: str, start: int = 0):
    """Read one public web page (HTML or PDF) and return its main text with its source fields.

    Skill `web-search`.
    """
    search_url()
    if start < 0:
        raise _error("read_web_page", f"start = {start}; expected 0 or more", "start")
    final, kind, content = await _fetch(url)
    is_pdf = kind == "application/pdf" or content[:5] == b"%PDF-"
    if not is_pdf and kind and not ("html" in kind or kind.startswith("text/")):
        raise _error("read_web_page", f"the page is {kind}; expected HTML or PDF", "url")
    fields = await asyncio.to_thread(_pdf, content) if is_pdf else _html(content, kind)
    text = fields.pop("text")
    end = start + PAGE_CHARACTERS
    return {
        "url": final,
        "site": urlsplit(final).hostname,
        "kind": "pdf" if is_pdf else "html",
        **fields,
        "length": len(text),
        "start": start,
        "text": text[start:end],
        "next_start": end if end < len(text) else None,
    }
