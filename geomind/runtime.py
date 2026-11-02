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

ROLES = ("analyst", "coordinator", "designer", "economist", "explainer", "summarizer", "verifier")
_FIXED = {
    "max_steps": 30,
    "retry_count": 3,
    "retry_delay": 0.5,
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
ADDED_SETTINGS = frozenset({"provider", "context_window", "cache_marked_models"})
_settings = ContextVar("geomind_settings", default=None)


def _listed(name):
    """Return the comma-separated items of an environment variable, or ``None``."""
    items = [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]
    return items or None


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
