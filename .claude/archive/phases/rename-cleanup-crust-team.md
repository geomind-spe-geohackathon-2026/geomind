# Remove the old Python package name

Prompt for Claude Code, run in `/Users/sahand/Desktop/crust-team`.

The agent Python package is `geomind` (`import geomind as gd`). Remove every reference to the old **Python package** (its imports and short alias, its root error class, the dependency in `pyproject.toml`, editable paths, and text that describes the package).

**Do not touch infrastructure or runtime names:** app name, Postgres database, MinIO bucket, InfluxDB org and bucket, container, network and volume names, environment variables of services, compose files, `infrastructure/` and the old domain all stay exactly as they are. When unsure whether a hit is the package or a runtime name, leave it and list it.

## Rules

- Other Claude sessions may work in sibling folders. Before editing a folder, check `git status` there; if it has uncommitted changes you did not make, skip it and report it.
- Do not touch `gemini/` or `infrastructure/`; only report hits found there.
- Develop on `main` and push `origin main` in each repository you change. Run that repository's fast tests and linters before committing; nothing may break.
- Keep each repository's conventions (`AGENTS.md`, `.claude/docs/`); no comments in code.

## Steps

1. **Find:** `grep -rIn -i` for the old package name and its alias in every folder of `crust-team` except `.git/`, `.venv/`, `node_modules/` and build outputs. Write the hits to `.tmp/rename-findings.md`, each marked **package** (to change) or **runtime/infrastructure** (to keep).
2. **Change the package hits** in `docs/`, `geomind/`, `backend/` and `frontend/`: old package name → `geomind`, old alias → `gd`, the old design file → `geomind-design.md`, the old phases folder → `phases/geomind/`. Delete sentences that only say the package was renamed, and the `CHANGELOG.md` rename line in `geomind/`.
3. **Old prompt copies:** list the old S1 run and prompt files in `crust-team/` and on the Desktop, then delete them.
4. **Check:** rerun the grep; every remaining hit must be a runtime or infrastructure name or inside `gemini/`.

## Report back

Per repository: files changed, commit hash, tests and lint result; every remaining hit with its reason.
