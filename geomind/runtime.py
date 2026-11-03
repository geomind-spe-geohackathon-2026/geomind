"""Context-local settings.

Settings live in one ``contextvars.ContextVar``, so a change applies to the current context only.
asyncio tasks and ``asyncio.to_thread`` workers start from a copy of their creator's context,
while new threads start from the defaults.
"""

import asyncio
import contextvars
import functools
import os
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar

from geomind.errors import UnknownNameError
from geomind.utils.context import ContextSetting
from geomind.utils.strings import did_you_mean

ROLES = ("analyst", "coordinator", "designer", "economist", "explainer", "summarizer", "verifier")
_FIXED = {
    "max_steps": 30,
    "request_timeout": 120.0,
    "prompt_caching": True,
    "tool_result_limit": 40_000,
    "delegate_summary_tokens": 500,
    "sandbox_timeout": "10min",
    "sandbox_memory": "1g",
    "sandbox_disk": "1g",
    "sandbox_cpu": 1,
    "compaction_threshold": 0.6,
    "compaction_keep_turns": 6,
    "analyst_model": None,
    "designer_model": None,
    "economist_model": None,
    "explainer_model": None,
    "verifier_model": None,
}
ADDED_SETTINGS = frozenset(
    {
        "provider",
        "context_window",
        "cache_marked_models",
        "compare_concurrency",
        "compare_retries",
        "gemini_threads",
    }
)
_settings = ContextVar("geomind_settings", default=None)


def _listed(name):
    """Return the comma-separated items of an environment variable, or ``None``."""
    items = [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]
    return items or None


RETRY_COUNT = 3
RETRY_DELAY_S = 0.5
"""The retries of a failed provider call and the first delay, doubled each time, unless set."""


def _number(name):
    """Return an environment variable as a number, or ``None`` when unset."""
    text = os.environ.get(name)
    return float(text) if text else None


def _integer(name):
    """Return an environment variable as an integer, or ``None`` when unset."""
    text = os.environ.get(name)
    return int(text) if text else None


def _defaults():
    """Return the default settings; environment variables choose models and providers.

    geomind holds no model id. ``GEOMIND_MODEL`` is the default model, ``GEOMIND_CHEAP_MODEL`` the
    model of the coordinator and the summarizer; unset means ``None``, and a real provider refuses
    to call. ``GEOMIND_PROVIDER`` lists the OpenRouter providers to try, ``GEOMIND_CONTEXT_WINDOW``
    sets the context window in tokens and ``GEOMIND_CACHE_MARKED_MODELS`` the model id prefixes
    that get cache breakpoints; unset means the provider's list, and none.
    ``GEOMIND_COMPARE_CONCURRENCY`` is how many families a comparison designs side by side; unset
    means one at a time. ``GEOMIND_COMPARE_RETRIES`` is how often a family gemini rejects is
    designed again; unset means never. ``GEOMIND_GEMINI_THREADS`` is the size of the thread pool
    gemini work runs in; unset means asyncio's default executor. ``GEOMIND_RETRY_COUNT`` and
    ``GEOMIND_RETRY_DELAY`` (seconds) set the backoff of a failed provider call.
    """
    cheap = os.environ.get("GEOMIND_CHEAP_MODEL") or None
    return {
        "default_model": os.environ.get("GEOMIND_MODEL") or None,
        **_FIXED,
        "coordinator_model": cheap,
        "summarizer_model": cheap,
        "provider": _listed("GEOMIND_PROVIDER"),
        "context_window": _integer("GEOMIND_CONTEXT_WINDOW"),
        "cache_marked_models": _listed("GEOMIND_CACHE_MARKED_MODELS"),
        "compare_concurrency": _integer("GEOMIND_COMPARE_CONCURRENCY"),
        "compare_retries": _integer("GEOMIND_COMPARE_RETRIES"),
        "gemini_threads": _integer("GEOMIND_GEMINI_THREADS"),
        "retry_count": _integer("GEOMIND_RETRY_COUNT") or RETRY_COUNT,
        "retry_delay": _number("GEOMIND_RETRY_DELAY") or RETRY_DELAY_S,
    }


def role_models():
    """Return the model id of each role from the settings; ``None`` where none is set."""
    return {role: get(f"{role}_model") or get("default_model") for role in ROLES}


def model_problems():
    """Return one line per role without a model, naming the setting that would give it one."""
    cheap_roles = ("coordinator", "summarizer")
    lines = []
    for role, model in role_models().items():
        if model is None:
            name = "GEOMIND_CHEAP_MODEL" if role in cheap_roles else "GEOMIND_MODEL"
            lines.append(f"{role}: set {name} or {role}_model")
    return lines


def missing_model_settings():
    """Return the environment variables whose absence leaves a role without a model."""
    cheap_roles = ("coordinator", "summarizer")
    missing = []
    for role, model in role_models().items():
        name = "GEOMIND_CHEAP_MODEL" if role in cheap_roles else "GEOMIND_MODEL"
        if model is None and name not in missing:
            missing.append(name)
    return missing


def state():
    """Return a copy of the current settings."""
    return dict(_settings.get() or _defaults())


def get(name):
    """Return one setting."""
    current = state()
    if name not in current:
        raise UnknownNameError(
            f"runtime: setting = {name!r}; expected a known setting{did_you_mean(name, current)}"
        )
    return current[name]


def load_state(mapping):
    """Replace the settings with a mapping that ``state()`` returned.

    A name this version added after the mapping was stored takes its default, so a run stored
    by an older version still resumes; any other missing name or an unknown name raises.
    """
    defaults = _defaults()
    missing = set(defaults) - set(mapping) - ADDED_SETTINGS
    if set(mapping) - set(defaults) or missing:
        raise UnknownNameError(
            f"runtime: settings = {sorted(mapping)}; expected every name of runtime.state()"
        )
    _settings.set({**defaults, **mapping})


def settings(**changes):
    """Change settings for a ``with`` block or a decorated call."""
    for name in changes:
        get(name)
    return ContextSetting(_settings, lambda current: {**(current or _defaults()), **changes})


_pools = {}


def _pool(size):
    """Return this process's pool of ``size`` gemini threads, made on first use."""
    if size not in _pools:
        _pools[size] = ThreadPoolExecutor(max_workers=size, thread_name_prefix="geomind-gemini")
    return _pools[size]


async def in_gemini_thread(function, *args, **kwargs):
    """Run gemini work off the event loop, with the caller's settings.

    NOTE: with ``gemini_threads`` set it runs in a pool of that many threads, so a long-running
    process has few threads and glibc few malloc arenas; unset, it runs as ``asyncio.to_thread``.
    """
    size = get("gemini_threads")
    if size is None:
        return await asyncio.to_thread(function, *args, **kwargs)
    call = functools.partial(contextvars.copy_context().run, function, *args, **kwargs)
    return await asyncio.get_running_loop().run_in_executor(_pool(size), call)
