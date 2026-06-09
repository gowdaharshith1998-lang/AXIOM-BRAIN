## Summary

-

## Type of Change

- [ ] Documentation
- [ ] Test
- [ ] Bug fix
- [ ] Feature
- [ ] Refactor
- [ ] CI/security/ops

## Verification

- [ ] `uv lock --check`
- [ ] `uv run ruff check src/ tests/ scripts/`
- [ ] `uv run ruff format --check src/ tests/ scripts/`
- [ ] `uv run mypy`
- [ ] `uv run pytest -q --maxfail=5 --cov=axiom --cov-report=xml --cov-fail-under=50`
- [ ] Frontend tests/build, if applicable
- [ ] Docs updated, if applicable

## Security Notes

Does this touch auth, vault, connector OAuth/webhooks, signing, policy, receipts, deployment, or dependencies?

- [ ] No
- [ ] Yes, notes below

## Screenshots Or Logs

Add screenshots, CLI output, logs, or API examples when useful.

## Related Issues

Closes #
