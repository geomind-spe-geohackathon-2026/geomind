# Project rules

These rules apply to everyone who works on geomind, people and agents alike.

## Models and tokens

- No live runs. Nothing calls a model provider or spends LLM tokens unless Sahand allows it.
- Tests and evals run offline on fake providers and recordings.
- DeepSeek only. Never use or add an Anthropic model id.
- The package holds no model id. A deployment names its models.

## Code

- No default values in package code: a value comes from the user, the case or a setting.
- Everything is general. No competition-specific numbers in the package.
- No comments in code, docstrings only. The few exceptions are in
  [conventions](../.claude/docs/conventions.md#comments).
- Frozen interfaces change only with a version raise, see
  [the change rule](../.claude/docs/api.md#frozen-interfaces).

## gemini

- gemini is the source of truth for physics, and it is read-only here: change it only in its own
  repository.
- Nothing is requested from gemini without Sahand's approval. Requests go on a list for him.
- Use only gemini's public API.

## Installs

- No `-e`, editable or path installs of another project.
- gemini is installed from its release wheel.
- Do not publish to PyPI: the name `geomind` there belongs to an unrelated, abandoned package.

## Branches and worktrees

- There are two long-lived branches: `dev` for all new work and `main` for stable releases.
- A change reaches `main` only by merging `dev`, after all tests pass locally.
- Any other branch is deleted after it is merged, or tagged if it must be kept.
- Worktree branches stay local and are removed after the merge.
- Every git worktree goes under the repository's own `.tmp/`, for example
  `git worktree add .tmp/worktrees/<name>`, never next to the repository.
- `.tmp/` is ignored and never tracked. Never `git add -f` anything under it.

## Changes

- A bug gets a failing test first; the fix makes it pass.
- Docs and `docs/CHANGELOG.md` change in the same commit as the behaviour they describe.
- Never shrink or delete recordings or goldens.
- A fast-tier test takes at most 1 s. Never raise this budget or skip a test to meet it.
- Before a commit, run `make test`, then `make test-all` and `make lint`.
- Test on local servers only, never on production.
