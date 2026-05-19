## Summary

<!-- One or two sentences describing what this PR does and why. -->

## Changes

<!-- Bullet list of what changed. -->

-

## Scope Check

- [ ] Change stays within source resolution + verification (or patch records / reconciliation)
- [ ] No subprocess execution / runner logic introduced (that's CoreRunner)
- [ ] No routing or planning logic introduced
- [ ] Force-push and PR-creation consent flags still gate destructive actions

## Testing

- [ ] Tests pass: `pytest -q`
- [ ] Linter passes: `ruff check src/`
- [ ] New behavior is covered by tests
- [ ] Failure paths tested (missing clone, mismatched SHA, push failure, etc.)

## Related Issues

<!-- Closes #N or References #N -->

## Notes for Reviewer

<!-- Anything non-obvious: edge cases, install_kind-specific behavior, follow-ups. -->
