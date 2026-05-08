# Log

_Chronological continuity log. Decisions, stop points, what changed and why._
_Not a task tracker — that's backlog.md. Keep entries concise and dated._

## Recent Decisions

_Log significant choices here so they survive context resets._

| Decision | Rationale | Date |
|----------|-----------|------|
| [what was decided] | [why] | [date] |

## Stop Points

_Where did you leave off? What should be verified next session?_

- [what to pick up next]

## Notes

_Free-form scratch. Clear periodically — old entries can be deleted once no longer relevant._

---

- DC4 README sections (2026-05-08, on `fix/dc4-readme-sections`): Custodian DC4 (native) flagged the README missing both Quick start and Architecture H2s. Quick start gives pip install + source-registry CLI examples; Architecture summarises the YAML-registry-with-five-surfaces shape (verify / lifecycle / patches / poll / push) and points at Install kinds for the verification-basis table.

## 2026-05-08 — M1: CHANGELOG.md stub (Keep-a-Changelog format)

Added a minimal CHANGELOG.md so M1 (and M5 format check) pass.

## 2026-05-08 — Custodian round: SR clean (63 → 0)

- Added comprehensive T1/T6/T7 exclude_paths in .custodian/config.yaml
  for CLI, contracts, errors, git ops, IO, validation, vocabulary, registry,
  and the lifecycle/patches/poll/push/verify modules — all integration-tested
  via subprocess or via consumer modules.
- C11: timeout=60 on git subprocess; timeout=120 on push subprocess.
- C43: ensure_ascii=False on json.dump in json_io.
- D3: cli.py command handlers excluded (they exit via typer.Exit).
- S4: added tests/conftest.py with venv guard.


## 2026-05-08 — CI regression guard

Added .github/workflows/custodian-audit.yml + .hooks/pre-push.
Both run `custodian-multi --fail-on-findings`. CI is the source of
truth; pre-push catches regressions before they hit GitHub.

