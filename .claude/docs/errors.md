# Errors

`geomind/errors/` defines every geomind exception class. Users reach them as `gd.errors.<Name>`.
It is a leaf package (`tests/unit/test_package_boundaries.py`).

Every class derives from `GeomindError` and from the matching built-in exception, so `except
ValueError` keeps catching `gd.errors.RequestError`. Catch `GeomindError` to handle every geomind
error. New code raises one of these classes for every deliberate error; the exceptions are
`geomind.utils`, which cannot import them, pydantic validators, which must raise `ValueError`, and
the Python protocol errors (`NotImplementedError`, and `AttributeError` from `__getattr__`).
`test_package_code_raises_geomind_errors` enforces this.

A permission denial is a tool result, not an exception.

## Classes

`base.py`:

- `GeomindError(Exception)`: root of every class below.

`agent.py`, defining agents and their answers:

- `DeclarationError(TypeError, ValueError)`: an agent, tool or permission defined wrongly: a
  declaration before `super().__init__()` or after `__init__`, an unknown or duplicate name, a tool
  function without annotations or docstring.
- `UnknownNameError(ValueError)`: an unknown prompt role, runtime setting, permission mode or
  effect.
- `OutputError(ValueError)`: a final answer does not validate against the agent's `Output`. The
  engine feeds it back to the model up to `max_retries`, then the run fails.

`run.py`, running:

- `RunError(RuntimeError)`: an operation that needs an active or a known run has none: `complete`
  outside a run, `Run.load` of an unknown run, a run that cannot continue, `run.start()` inside an
  event loop.
- `RequestError(ValueError)`: an unknown or already answered request id, or an answer of the wrong
  shape.
- `StateError(ValueError)`: a change of the problem state is invalid; it becomes a tool result whose
  message tells the model how to fix the patch.
- `ReplayError(RuntimeError)`: a replay differs from its recording; the message names the first
  differing step; for a log older than the case lead it says the log can be read, shown and
  exported, but not re-run, and keeps that first difference.
- `LoopError(RuntimeError)`: a loop state that does not fit the loop.
- `BudgetError(ValueError)`: a budget set up wrongly, such as a `ProjectBudget` with no cap.

`services.py`, what the harness calls:

- `ProviderError(RuntimeError)`: an LLM call failed, with `status` and `is_retryable`. It ends the
  run with `stop_reason="error"` after retries and fallbacks.
- `ToolError(RuntimeError)`: a tool failed deliberately, timed out or was interrupted by a crash.
  It becomes a tool result. `code` is one of the [error codes](tools.md#error-results), default
  `invalid_input`, and `path` the input field at fault.
- `NotImplementedYet(NotImplementedError)`: a capability has its final signature and is not built
  yet; the message names its phase, as in `simulate comes in S2b`. In a tool it becomes an error
  result with `code: "not_implemented"`, so the model does not retry. In a loop or a hook it ends the
  run with `stop_reason="not_implemented"`.

## Message style

Write `<where>: <field> = <value>; expected <what>[; did you mean 'x'?]`. Use
`geomind.utils.strings.did_you_mean` for the suggestion and `join_names` for lists of valid names.

## Adding a class

Add a class only for a situation no existing class describes. Put it in the file of its topic,
derive it from `GeomindError` and from the matching built-in exception, give it a one-line docstring
saying when it is raised, export it in `geomind/errors/__init__.py`, and test it in the mirrored
file under `tests/unit/errors/`. Then update this document.
