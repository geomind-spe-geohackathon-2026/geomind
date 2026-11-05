"""The web tools: a page is read only from a public http(s) host."""

import pytest

from geomind.errors import ToolError
from geomind.tools import web


@pytest.mark.parametrize(
    "url", ["ftp://example.org/a", "https://user:pw@example.org/", "http://127.0.0.1/"]
)
async def test_a_url_that_is_no_public_http_page_is_refused(url):
    """Another scheme, credentials in the URL and a private host never reach the network."""
    with pytest.raises(ToolError):
        await web._checked(url)


def test_an_unset_search_url_is_not_allowed_and_names_its_variable():
    """No default: the setting is named."""
    from geomind import runtime

    with runtime.settings(search_url=None):
        with pytest.raises(ToolError, match="GEOMIND_SEARCH_URL"):
            web.search_url()
