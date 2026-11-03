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

ROLES = (
    "analysislead",
    "caselead",
    "coordinator",
    "designlead",
    "economist",
    "explainer",
    "geoscientist",
    "reviewer",
    "summarizer",
    "processengineer",
    "integrationengineer",
    "reservoirengineer",
    "wellengineer",
    "energysystemsengineer",
    "projectlead",
    "supportlead",
    "curator",
)
"""Every agent that calls a model, by its class name in lower case; each has its own setting."""
_FIXED = {
    "request_timeout": 120.0,
    "prompt_caching": True,
    "tool_result_limit": 40_000,
    "delegate_summary_tokens": 500,
    "compaction_threshold": 0.6,
    "compaction_keep_turns": 6,
}
REMOVED_SETTINGS = frozenset(
    {
        "default_model",
        "sandbox_timeout",
        "sandbox_memory",
        "sandbox_disk",
        "sandbox_cpu",
        "analyst_model",
        "designer_model",
        "verifier_model",
        "formulator_model",
    }
)
"""Names a run stored by an earlier version may hold; a stored run with them still resumes."""
ADDED_SETTINGS = frozenset(
    {
        "provider",
        "context_window",
        "cache_marked_models",
        "compare_concurrency",
        "compare_retries",
        "gemini_threads",
        "design_concurrency",
        "engineer_max_steps",
        *(f"{role}_model" for role in ROLES),
    }
)
_settings = ContextVar("geomind_settings", default=None)


def _listed(name):
    """Return the comma-separated items of an environment variable, or ``None``."""
    items = [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]
    return items or None


RETRY_SETTINGS = {
    "retry_count": "GEOMIND_RETRY_COUNT",
    "retry_delay": "GEOMIND_RETRY_DELAY",
    "max_steps": "GEOMIND_MAX_STEPS",
    "max_output_tokens": "GEOMIND_MAX_OUTPUT_TOKENS",
    "memory": "GEOMIND_MEMORY",
    "design_concurrency": "GEOMIND_DESIGN_CONCURRENCY",
    "engineer_max_steps": "GEOMIND_ENGINEER_MAX_STEPS",
}
"""The settings a live run needs beside its models, by the environment variable that sets each.

NOTE: ``max_steps`` is the steps an agent takes before the run asks the user to continue; every
run needs it, so a run without it refuses to start."""
MEMORY_SETTINGS = {
    "memory_dir": "GEOMIND_MEMORY_DIR",
    "memory_similarity": "GEOMIND_MEMORY_SIMILARITY",
}
"""What a memory that is on needs: where it lives and how alike a past design must be."""


def _number(name):
    """Return an environment variable as a number, or ``None`` when unset."""
    text = os.environ.get(name)
    return float(text) if text else None


def _integer(name):
    """Return an environment variable as an integer, or ``None`` when unset."""
    text = os.environ.get(name)
    return int(text) if text else None


def model_variable(role):
    """Return the environment variable that names the model of ``role``."""
    return f"GEOMIND_{role.upper()}_MODEL"


def _defaults():
    """Return the default settings; environment variables choose models and providers.

    geomind holds no model id. Each role's model is its own ``GEOMIND_<ROLE>_MODEL``, such as
    ``GEOMIND_DESIGNLEAD_MODEL``, with no fallback to another role's; unset means ``None``, and a
    real provider refuses to call. ``GEOMIND_PROVIDER`` lists the OpenRouter providers to try,
    ``GEOMIND_CONTEXT_WINDOW``
    sets the context window in tokens and ``GEOMIND_CACHE_MARKED_MODELS`` the model id prefixes
    that get cache breakpoints; unset means the provider's list, and none.
    ``GEOMIND_COMPARE_CONCURRENCY`` is how many families a comparison designs side by side; unset
    means one at a time. ``GEOMIND_COMPARE_RETRIES`` is how often a family gemini rejects is
    designed again; unset means never. ``GEOMIND_GEMINI_THREADS`` is the size of the thread pool
    gemini work runs in; unset means asyncio's default executor. ``GEOMIND_RETRY_COUNT`` and
    ``GEOMIND_RETRY_DELAY`` (seconds) set the backoff of a failed provider call; geomind holds
    no value for them, so a live run without them is refused, and a scripted provider, unset,
    makes one attempt.
    """
    return {
        **_FIXED,
        **{f"{role}_model": os.environ.get(model_variable(role)) or None for role in ROLES},
        "provider": _listed("GEOMIND_PROVIDER"),
        "context_window": _integer("GEOMIND_CONTEXT_WINDOW"),
        "cache_marked_models": _listed("GEOMIND_CACHE_MARKED_MODELS"),
        "compare_concurrency": _integer("GEOMIND_COMPARE_CONCURRENCY"),
        "compare_retries": _integer("GEOMIND_COMPARE_RETRIES"),
        "gemini_threads": _integer("GEOMIND_GEMINI_THREADS"),
        "max_steps": _integer("GEOMIND_MAX_STEPS"),
        "max_output_tokens": _integer("GEOMIND_MAX_OUTPUT_TOKENS"),
        "design_concurrency": _integer("GEOMIND_DESIGN_CONCURRENCY"),
        "engineer_max_steps": _integer("GEOMIND_ENGINEER_MAX_STEPS"),
        "memory": os.environ.get("GEOMIND_MEMORY") or None,
        "memory_dir": os.environ.get("GEOMIND_MEMORY_DIR") or None,
        "memory_similarity": _number("GEOMIND_MEMORY_SIMILARITY"),
        "retry_count": _integer("GEOMIND_RETRY_COUNT"),
        "retry_delay": _number("GEOMIND_RETRY_DELAY"),
    }


def role_models():
    """Return the model id of each role from the settings; ``None`` where none is set."""
    return {role: get(f"{role}_model") for role in ROLES}


def model_problems():
    """Return one line per role without a model, naming the setting that would give it one."""
    lines = [
        f"{role}: set {model_variable(role)} or {role}_model"
        for role, model in role_models().items()
        if model is None
    ]
    for setting, name in RETRY_SETTINGS.items():
        if get(setting) is None:
            lines.append(f"retries: set {name} or {setting}")
    return lines + memory_problems()


def memory_problems():
    """Return one line per memory setting a run lacks: the switch, and with it on, the rest."""
    switch = get("memory")
    if switch is None:
        return []
    if switch not in ("on", "off"):
        return [f"memory: GEOMIND_MEMORY = {switch!r}; expected on or off"]
    if switch == "off":
        return []
    return [
        f"memory: set {name} or {setting}"
        for setting, name in MEMORY_SETTINGS.items()
        if get(setting) is None
    ]


def missing_model_settings():
    """Return the environment variables a live run lacks: a role's model, the retry settings."""
    missing = [model_variable(role) for role, model in role_models().items() if model is None]
    missing += [name for setting, name in RETRY_SETTINGS.items() if get(setting) is None]
    if get("memory") == "on":
        missing += [name for setting, name in MEMORY_SETTINGS.items() if get(setting) is None]
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

    A name this version added after the mapping was stored takes its default, and a name of
    ``REMOVED_SETTINGS`` is dropped, so a run stored by an older version still resumes; any other
    missing name or an unknown name raises.
    """
    defaults = _defaults()
    mapping = {key: value for key, value in mapping.items() if key not in REMOVED_SETTINGS}
    missing = set(defaults) - set(mapping) - ADDED_SETTINGS
    if set(mapping) - set(defaults) or missing:
        raise UnknownNameError(
            f"runtime: settings = {sorted(mapping)}; expected every name of runtime.state()"
        )
    _settings.set({**defaults, **mapping})


def stored(mapping):
    """Return the settings a stored run names, without those this version removed."""
    return {name: value for name, value in mapping.items() if name not in REMOVED_SETTINGS}


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
