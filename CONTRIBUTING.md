# Contributing to Budget Me

Budget Me is an experimental personal-finance blueprint maintained on a
best-effort basis. Issues and pull requests are welcome, but there is no promise
of review, response time, release cadence, or long-term support.

## License and sign-off

The project is licensed under the [Apache License 2.0](LICENSE). Unless a
separate agreement says otherwise, a contribution submitted for inclusion is
licensed under the same terms.

Use the [Developer Certificate of Origin](https://developercertificate.org/) to
certify that you have the right to submit your work:

```bash
git commit -s
```

The sign-off must use a name and email you are willing to publish in Git
history. A contributor license agreement is not required.

## Development setup

```bash
git clone https://github.com/jyaunches/budget-me.git
cd budget-me
uv sync --frozen --all-extras
make lint
make test
```

Use Python 3.11 or 3.12. Keep dependency changes in `pyproject.toml` and
`uv.lock` together.

## Financial-data safety

Use only synthetic fixtures and disposable databases in contributions.

Never include:

- credentials, database URLs, tokens, encryption keys, or provider identifiers;
- names, email addresses, phone or chat identifiers;
- account masks, merchants, dates, amounts, balances, liabilities, statements,
  screenshots, or raw provider payloads from a real household;
- database dumps, exported rules, CI logs, or application logs containing
  financial details; or
- copied configuration from a private installation.

Use unmistakably synthetic values such as `test-client`, zero UUIDs,
`Example Bank`, and purpose-built disposable database names.

## Checks

Run before submitting:

```bash
make lint
uv run ruff format --check src tests
make test
make audit
```

The ordinary unit suite must not require provider credentials or a database.

Database integration tests require an explicitly named disposable PostgreSQL
database:

```bash
BUDGET_ME_ALLOW_DATABASE_TESTS=1 \
BUDGET_ME_TEST_DATABASE_URL=postgresql://USER:PASSWORD@127.0.0.1:5432/budget_me_test \
make test-database-integration
```

The Plaid provider suite is Sandbox-only and has a separate gate documented in
[self-hosting](docs/self-hosting.md#optional-plaid-provider-tests). Never point
any suite at a household database.

## Database changes

For a schema change:

1. Add a forward-only Alembic migration.
2. Enable RLS in the creation migration for every new public-schema table.
3. Keep downgrade behavior explicit about data loss.
4. Add empty-database migration and upgraded-schema coverage.
5. Run `uv run alembic current --check-heads` and `uv run alembic check`.
6. Describe backup and operator implications in the pull request.

Do not rewrite a migration that may already have been applied.

## Categorization rules

The tracked YAML contains only the public category taxonomy and generic starter
mappings. Household-specific overrides and learned rules belong in PostgreSQL.

When changing the public rules:

- use generic merchant names that do not reveal a household;
- avoid overly broad patterns;
- preserve valid YAML and category names; and
- add tests for precedence, disabled mappings, and false positives.

## Pull requests

Keep changes focused and explain:

- the problem and intended behavior;
- security, privacy, migration, and provider effects;
- tests run and tests intentionally omitted;
- any new data processor, network call, secret, permission, or recurring cost;
  and
- whether documentation or operator action is required.

Do not weaken Sandbox defaults, authentication, write confirmations, exact
revision checks, TLS validation, or disposable-test guards merely to make a test
pass.
