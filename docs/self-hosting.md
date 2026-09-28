# Self-hosting Budget Me

This reference supplies the commands and provider details behind
[SETUP.md](SETUP.md). It assumes one trusted household and begins with Plaid
Sandbox.

> Budget Me is an experimental blueprint without a maintenance or
> security-response commitment. Review the code and provider terms for your own
> installation before connecting live financial accounts.

## What you need

- Git
- Python 3.11 or 3.12
- [uv](https://docs.astral.sh/uv/)
- A dedicated [Supabase](https://supabase.com/) project
- A [Plaid](https://dashboard.plaid.com/) team
- Docker for the container build or database integration tests
- Optional GitHub, Telegram, Render, and Google Cloud accounts

Use a separate private repository for operational configuration. Never commit
`.env`, database dumps, screenshots, statements, provider exports, or
household-specific categorization rules.

### Free-tier caveats

These terms were checked in September 2026 and may change:

- [Supabase Free](https://supabase.com/docs/guides/platform/billing-on-supabase)
  currently provides two active projects and a 500 MB database quota per
  project. Projects with low activity may pause, and automatic backups are not
  included.
- [Plaid Sandbox](https://plaid.com/docs/sandbox/) is free and synthetic.
  Eligible US and Canada teams created on or after April 15, 2026 can apply for
  a free Trial with up to 10 lifetime Production Items. Removing an Item does
  not restore a slot.
- [GitHub Actions](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
  standard hosted runners are free for public repositories. Private
  repositories use the account's included allowance.
- [Render Free](https://render.com/docs/free) web services sleep after idle
  periods, use an ephemeral filesystem, share monthly usage limits, and are
  explicitly not intended for production applications.
- Telegram bot messaging is generally free. Model APIs, durable backup storage,
  live Plaid products outside eligible Trial use, and production-grade hosting
  may incur charges.

## 1. Install the project

Clone the repository and check out a reviewed commit:

```bash
git clone https://github.com/jyaunches/budget-me.git
cd budget-me
git checkout REVIEWED_COMMIT_SHA
uv sync --frozen --all-extras
```

Verify the source before adding secrets:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest tests/unit -q
```

To build the supplied container from that exact checkout:

```bash
docker build --tag budget-me:REVIEWED_COMMIT_SHA .
docker image inspect budget-me:REVIEWED_COMMIT_SHA --format '{{.Id}}'
```

Do not use a moving `main` or `latest` image for an unreviewed schema
migration.

## 2. Configure Supabase and application secrets

### Create the project

1. Create a dedicated project in the
   [Supabase Dashboard](https://supabase.com/dashboard).
2. Choose the data region and save a strong database password.
3. Open **Connect** and copy the **Session pooler** connection string on port
   `5432`.
4. Percent-encode reserved password characters if necessary.

The Session pooler works with local clients, GitHub-hosted runners, and
IPv4-only hosts. Never paste its URL into chat, an issue, a screenshot, or shell
history.

### Create the local environment

```bash
cp .env.example .env
chmod 600 .env
make generate-key
```

Store the generated Fernet key in a password manager, then edit `.env`
privately:

```dotenv
ENVIRONMENT=development
DATABASE_URL=postgresql://postgres.PROJECT_REF:DATABASE_PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres
APP_TOKEN_ENC_KEY=GENERATED_FERNET_KEY
PLAID_CLIENT_ID=PLAID_CLIENT_ID
PLAID_SECRET=PLAID_SANDBOX_SECRET
PLAID_ENV=sandbox
AUTH_REQUIRED=false
AUTH_ALLOWED_EMAILS=
LOG_LEVEL=INFO
```

The Fernet key encrypts Plaid access tokens before database storage. Losing or
replacing it makes existing encrypted tokens unreadable unless they are
re-encrypted; retain it separately from database backups.

Confirm that secrets remain untracked:

```bash
git check-ignore -v .env
git status --short
```

### Initialize the database

Schema initialization is an explicit operator write:

```bash
make db-migrate
uv run alembic current --check-heads
uv run alembic check
```

In the Supabase SQL Editor, verify that every public financial table has RLS
enabled:

```sql
select tablename, rowsecurity
from pg_tables
where schemaname = 'public'
order by tablename;
```

Stop if a financial table reports `rowsecurity = false`.

Budget Me connects directly to PostgreSQL. A database-owner connection can
bypass RLS, so RLS protects the Supabase API surface but is not the
application's only authorization control. Use a least-privilege runtime role
before exposing the application to the internet.

Packaged categorization rules live in
`src/budget_me/data/categorization-rules.yaml`. Installation-specific
overrides and learned rules belong in PostgreSQL, not in the tracked file.
Inspect counts without printing patterns:

```bash
uv run budget-me rules status
```

## 3. Link Plaid Sandbox and run the first sync

1. Create or sign in to a Plaid team.
2. Enable Transactions and Liabilities.
3. Copy the team client ID and **Sandbox** secret into `.env`.
4. Keep `PLAID_ENV=sandbox`.

Start Streamlit:

```bash
make streamlit
```

This binds to `127.0.0.1`. Keep it loopback-only while
`AUTH_REQUIRED=false`.

Open [http://localhost:8501](http://localhost:8501), choose **Link Account**,
and complete Plaid Link yourself. Plaid's current
[Sandbox credentials](https://plaid.com/docs/sandbox/test-credentials/) provide
synthetic users and institutions.

Run the initial synchronization:

```bash
uv run budget-me status
uv run budget-me sync
uv run budget-me liabilities
```

Refresh Streamlit and confirm:

- expected synthetic accounts and balances;
- transaction history;
- supported credit-card or loan liability details;
- categorization-rule counts; and
- no live institution or Production Item.

Liabilities is part of the complete application setup because the Credit Cards
and Debt screens need supported APR, payment, and loan details. When Plaid does
not provide a field, leave it unknown until the human supplies reviewed data.

### Optional Plaid provider tests

The provider suite makes real Plaid Sandbox calls and writes only to a dedicated
local PostgreSQL database named exactly `budget_me_plaid_test`. It is excluded
from ordinary tests and requires explicit opt-ins:

```bash
export BUDGET_ME_ALLOW_PLAID_PROVIDER_TESTS=1
export PLAID_ENV=sandbox
export BUDGET_ME_PLAID_TEST_CLIENT_ID=YOUR_SANDBOX_CLIENT_ID
export BUDGET_ME_PLAID_TEST_SECRET=YOUR_SANDBOX_SECRET
export BUDGET_ME_PLAID_TEST_DATABASE_URL=postgresql://USER:PASSWORD@127.0.0.1:5432/budget_me_plaid_test
make test-plaid-integration
unset BUDGET_ME_ALLOW_PLAID_PROVIDER_TESTS \
  BUDGET_ME_PLAID_TEST_CLIENT_ID \
  BUDGET_ME_PLAID_TEST_SECRET \
  BUDGET_ME_PLAID_TEST_DATABASE_URL
```

Use a private terminal that does not record the exported values. Never reuse the
application database.

## 4. Optional GitHub, Telegram, and Render services

### GitHub synchronization

The included `nightly-sync.yml` is manual-only. It defaults to no writes and
requires an exact reviewed 40-character commit SHA for a write-enabled run.

Add these Actions secrets to a private operational repository:

- `DATABASE_URL`
- `APP_TOKEN_ENC_KEY`
- `PLAID_CLIENT_ID`
- `PLAID_SECRET`

Optional categorization uses `ANTHROPIC_API_KEY` and `TAVILY_API_KEY`.
Enabling them sends merchant descriptors, and potentially search-result
snippets, to those providers.

Run a no-write dispatch first:

```bash
gh workflow run nightly-sync.yml
```

For an intentional Sandbox write:

```bash
REVIEWED_COMMIT_SHA="$(git rev-parse HEAD)"
gh workflow run nightly-sync.yml \
  --field reviewed_commit_sha="$REVIEWED_COMMIT_SHA" \
  --field confirm_database_writes=true \
  --field plaid_environment=sandbox \
  --field auto_categorize=false \
  --field send_telegram_summary=false
gh run watch
```

Adding a `schedule` trigger alone does not authorize writes because scheduled
events do not provide the dispatch inputs. An unattended design must preserve
an affirmative write boundary, a fixed intended environment, and reviewed
source selection.

### Telegram notifications

Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_IDS` only after approving
Telegram as a financial-data processor. Outbound summaries may include failed
institution names and, when categorization runs, merchant names, dates, amounts,
and counts. The repository contains no inbound Telegram or chat-to-agent
workflow.

### Render hosting

The supplied `render.yaml` is for hobby and Sandbox use and disables automatic
deployment from moving `main`. Set these values directly in Render:

- `DATABASE_URL`
- `APP_TOKEN_ENC_KEY`
- `PLAID_CLIENT_ID`
- `PLAID_SECRET`
- `PLAID_REDIRECT_URI` for Plaid OAuth
- `AUTH_ALLOWED_EMAILS`
- `AUTH_COOKIE_SECRET`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `AUTH_REDIRECT_URI`

Keep `AUTH_REQUIRED=true` and use a non-empty trusted-email allowlist. Create a
Google Web application OAuth client and register:

```text
https://YOUR_SERVICE.onrender.com/oauth2callback
```

Set `AUTH_REDIRECT_URI` to that exact URL. If using an OAuth Plaid
institution, register and configure its exact HTTPS redirect URI as well.
Verify that an allowlisted identity can enter and an unlisted identity cannot
access any page.

Do not use the Free blueprint as production hosting for live financial data.

## Backups and recovery

Supabase Free does not include automatic backups. Before live use:

- choose encrypted off-site storage and retention;
- back up both schema and data;
- preserve `APP_TOKEN_ENC_KEY` separately from the database dump;
- test restoration into a new disposable database;
- record how to revoke and relink Plaid Items if the key is lost; and
- protect categorization rules, notes, and raw Plaid data as financial records.

A dump is plaintext until encryption succeeds. Use restrictive permissions,
avoid placing URLs in command history, encrypt before moving the artifact, and
remove temporary plaintext through an approved local procedure.

A backup is not proven until a restore test verifies the Alembic head,
application startup, aggregate table counts, and access control against the
restored database. Never rehearse against the live database.

## Security minimums

Budget Me can store encrypted Plaid tokens and unencrypted account identifiers,
balances, transactions, merchants, liabilities, budgets, forecasts,
reimbursements, notes, and raw provider objects.

- Keep secrets, dumps, exports, statements, screenshots, and generated JSON out
  of Git, issues, CI artifacts, and shared chat.
- Use unique secrets per installation and restrict provider-team membership.
- Require authentication and an owner allowlist for hosted access.
- Use a least-privilege runtime database role and verify RLS.
- Review every optional data processor before supplying an API key.
- Keep detailed financial data out of logs and notifications.
- Rotate a credential immediately if it appears in history or public output.
- Maintain a dependency-upgrade and security-review process.
- Document data export, Plaid Item revocation, and complete deletion, including
  backups.

See [SECURITY.md](../SECURITY.md).

## Troubleshooting

### Supabase connection fails

- Confirm that the project is active.
- Copy a fresh Session pooler URI from **Connect**.
- Check password URL encoding.
- Confirm the canonical variable is `DATABASE_URL`.
- Never paste the URL into a bug report.

### Alembic fails

- Stop rather than continuing with a partial schema.
- Confirm the URL targets the intended dedicated project.
- Report only revision IDs and a redacted error.
- Rehearse upgrades on a restored or disposable database first.

### Plaid Link shows no live bank

Sandbox intentionally offers test institutions and synthetic data. Live
institutions require eligible Trial or Production access, and OAuth support
depends on Plaid Dashboard configuration.

### Data is unavailable after inactivity

Check whether Supabase paused the Free project. Resume it in the dashboard and
use the tested backup if the project cannot be recovered.

### Hosted login fails

Verify the Google OAuth callback, `AUTH_REDIRECT_URI`, cookie secret,
`AUTH_REQUIRED=true`, and the exact normalized email in
`AUTH_ALLOWED_EMAILS`.
