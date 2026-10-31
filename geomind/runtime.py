"""Context-local settings.

Settings live in one ``contextvars.ContextVar``, so a change applies to the current context only.
asyncio tasks and ``asyncio.to_thread`` workers start from a copy of their creator's context,
while new threads start from the defaults.
"""

import os
from contextvars import ContextVar

from geomind.errors import UnknownNameError
from geomind.utils.context import ContextSetting
from geomind.utils.strings import did_you_mean

FIXED_DEFAULT_MODEL = "anthropic/claude-sonnet-5.5"
FIXED_CHEAP_MODEL = "anthropic/claude-haiku-5.5"
_FIXED = {
    "max_steps": 30,
    "retry_count": 3,
    "retry_delay": 0.5,
    "request_timeout": 120.0,
    "tool_result_limit": 40_000,
    "delegate_summary_tokens": 500,
    "sandbox_timeout": "10min",
    "sandbox_memory": "1g",
    "sandbox_disk": "1g",
    "sandbox_cpu": 1,
    "compaction_threshold": 0.6,
    "compaction_keep_turns": 6,
    "analyst_model": None,
    "coordinator_model": FIXED_CHEAP_MODEL,
    "designer_model": None,
    "economist_model": None,
    "explainer_model": None,
    "summarizer_model": FIXED_CHEAP_MODEL,
    "verifier_model": None,
}
_settings = ContextVar("geomind_settings", default=None)


def _defaults():
    """Return the default settings; ``GEOMIND_MODEL`` chooses the default model."""
    return {"default_model": os.environ.get("GEOMIND_MODEL", FIXED_DEFAULT_MODEL), **_FIXED}


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
    """Replace the settings with the complete mapping that ``state()`` returns."""
    if set(mapping) != set(_defaults()):
        raise UnknownNameError(
            f"runtime: settings = {sorted(mapping)}; expected every name of runtime.state()"
        )
    _settings.set(dict(mapping))


def settings(**changes):
    """Change settings for a ``with`` block or a decorated call."""
    for name in changes:
        get(name)
    return ContextSetting(_settings, lambda current: {**(current or _defaults()), **changes})
