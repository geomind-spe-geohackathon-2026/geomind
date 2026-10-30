# Public API

Use `import swarmax as sx`. The curated top level is `Run`, `Agent`, `Engine`, `Tool`, `tool`,
`Prompt`, `Model`, `Output`, `Context`, `Message`, `Action`, `Request`, `Allow`, `Deny`,
`Permissions`, `RunResult`, `runlog`, `agents`, `tools`, `loops`, `hooks`, `callbacks`, `providers`,
`sandbox`, `stores`, `testing`, `runtime`, `errors` and `__version__`.
`tests/unit/test_public_api.py` pins this list. New top-level names require a concrete common user
workflow, documentation, and a public-API test.

`Run` is the facade the backend uses. `Engine` is the lower layer for tests, evals and custom
loops. `sx.stores` exposes `MemoryRunStore`, `FileRunStore`, `MemoryWorkspace` and `FileWorkspace`.

```python
import swarmax as sx

result = sx.Run(message="Say hello").start()
print(result.answer, result.usage)
```
