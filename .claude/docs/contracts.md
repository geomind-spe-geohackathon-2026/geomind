# Contracts

How swarmax implements the backend contract: [contracts.md](../../../docs/contracts.md), version 2,
sections 2 and 3. A change to the contract is a change to that file first, announced to all
repositories. Status: planned; the table is filled as each step lands.

## Proposed changes

These are additions the contract does not list yet; nothing in it was changed.

- `error` as an eighth internal event type: see [events.md](events.md).
- `load_events(run_id)` as a ninth `RunStore` method. The contract leaves it out, yet continuing a
  run whose process died needs the events after the last checkpoint. A store without it can still
  pause and resume from its checkpoint; `resume()` without arguments then raises `RunError`
  instead of repeating recorded calls. `Engine.replay` needs it too.
