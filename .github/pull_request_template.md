## Summary

Describe the problem and the focused solution.

## Safety and operational impact

- [ ] I used only synthetic data; this change contains no credentials or household financial information.
- [ ] I reviewed changes to authentication, authorization, secrets, logging, external calls, and retained data.
- [ ] I documented any schema migration, provider action, new data processor, permission, or recurring cost.
- [ ] I updated user or operator documentation where needed.

## Verification

List the commands run and their redacted results. Do not paste secret-bearing logs.

- [ ] `make lint`
- [ ] `uv run ruff format --check src tests`
- [ ] `make test`
- [ ] `make audit`

Database and Plaid integration tests must use explicitly authorized disposable, synthetic environments. Note any intentionally omitted checks and why.
