# Agent-guided Budget Me setup

This guide helps one person or trusted household set up Budget Me with a
coding-agent harness. It keeps provider approval and financial judgment with the
human while giving the agent a clear sequence to follow.

> Start with Plaid Sandbox and synthetic data. A working Sandbox installation
> does not prove that a live deployment is secure, backed up, affordable, or
> supported by every institution.

## How to use this guide

Start your agent with:

> Guide me through `docs/SETUP.md` one step at a time. Read the linked
> documentation before acting. Explain what will happen, distinguish your work
> from mine, pause before database writes or provider changes, validate each
> result, and never ask me to paste a secret into chat.

Use these sources of truth:

- [Self-hosting Budget Me](self-hosting.md) for commands, provider procedures,
  backups, and troubleshooting.
- [`.env.example`](../.env.example) for supported configuration.
- [Security policy](../SECURITY.md) for sensitive-data boundaries.

## Rules for the coding agent

Before each step:

1. Inspect the current repository and read the linked reference section.
2. Explain the purpose, expected result, and external or financial effect.
3. Label actions as **Agent** or **Human**.
4. Ask before database writes, provider changes, automation, or adding an
   external data processor.
5. Validate without printing credentials or household data.

The agent must never:

- ask the human to paste passwords, database URLs, API secrets, encryption
  keys, statements, or exported transactions into chat;
- echo secret-bearing files or copy their contents into logs, issues, commits,
  or screenshots;
- accept billing, switch Plaid to Production, schedule writes, or close a
  financial period without explicit human approval;
- invent balances, liabilities, account relationships, categories, or
  reconciliation decisions; or
- treat unit tests as proof that Plaid Link, OAuth, or a provider dashboard is
  configured correctly.

If the harness provides Budget Me skills, use the relevant setup, Supabase,
Plaid, categorization, snapshot, or Render skill. Skills are guidance only and
do not grant authority to make human decisions.

## 1. Choose the installation shape

The recommended first installation is:

- one person or trusted household;
- one dedicated Supabase project;
- Plaid Sandbox and synthetic accounts;
- Streamlit bound to the local machine;
- manual synchronization; and
- no optional processors until the core path works.

**Agent**

- Explain Streamlit, Supabase, Plaid, the Fernet key, and the optional services.
- Confirm this is a new database.
- Record which optional services the human may want after local validation.

**Human**

- Choose the coding-agent harness and approve any model provider that may
  process financial information.
- Confirm the Sandbox-first plan.

**Complete when:** no live credentials or household data have been introduced.

## 2. Install an exact revision

**Agent**

- Verify Git, Python 3.11 or 3.12, and `uv`.
- Clone or inspect the repository.
- Ask the human which commit to use instead of silently following a moving
  branch.
- Install the checked-in dependency lock without changing it.

**Human**

- Approve the repository, local directory, and reviewed commit.
- Install any missing system prerequisite that requires elevated access.

**Complete when:** the approved source is checked out and
`uv sync --frozen --all-extras` succeeds without provider credentials.

See [Install the project](self-hosting.md#1-install-the-project).

## 3. Configure Supabase and application secrets

Supabase stores the application data. `APP_TOKEN_ENC_KEY` is a Fernet key
owned by this installation; it encrypts Plaid access tokens before database
storage and is separate from the database password and Plaid secret.

**Agent**

- Copy `.env.example` to the ignored `.env` file and restrict its
  permissions.
- Tell the human where to enter each value, without receiving or displaying the
  value.
- After approval, initialize the empty schema and verify the Alembic head and
  RLS state.
- Confirm that `.env` remains ignored.

**Human**

- Create a dedicated Supabase project and save its database password.
- Copy the Session pooler connection string from **Connect** into `.env`
  privately as `DATABASE_URL`.
- Run `make generate-key`, save the result in a password manager, and enter it
  privately as `APP_TOKEN_ENC_KEY`.
- Explicitly authorize the schema initialization.

**Complete when:** the new database is at the expected migration head, its
financial tables have RLS enabled, and the Fernet key has a protected backup.

See [Supabase and application secrets](self-hosting.md#2-configure-supabase-and-application-secrets).

## 4. Configure Plaid Sandbox

Transactions provides account activity. Liabilities provides supported
credit-card and loan details used by the debt-related screens.

**Agent**

- Keep `PLAID_ENV=sandbox`.
- Explain why a complete setup enables both Transactions and Liabilities.
- Start Streamlit locally and guide the human to **Link Account**.
- Validate status, transactions, balances, and liability synchronization.

**Human**

- Create a Plaid team and accept its terms.
- Enable Transactions and Liabilities.
- Enter the Sandbox client ID and secret into `.env` privately.
- Personally complete Link, consent, and any OAuth prompts.

**Complete when:** synthetic Items, accounts, balances, transactions, and
supported liabilities appear, with no live institution connected.

See [Link Plaid Sandbox](self-hosting.md#3-link-plaid-sandbox-and-run-the-first-sync).

## 5. Review the application

**Agent**

Walk through:

1. Accounts
2. Transactions
3. Credit Cards
4. Debt
5. Budget
6. Yearly Forecast
7. Monthly Snapshot

Use packaged categorization rules first. Enable external inference or merchant
search only after the human approves those providers to receive merchant
descriptors.

**Human**

- Confirm account names and exclusions.
- Resolve categories, reimbursements, and projects.
- Confirm card-paying accounts, payment strategies, minimums, APRs, and
  promotional expirations.
- Verify budgets and forecasts.
- Approve every reconciliation and month-close decision.

**Complete when:** missing information remains explicitly unknown rather than
being guessed.

## 6. Protect the installation

**Agent**

- Explain that a database backup is unusable for encrypted Plaid tokens without
  the matching Fernet key.
- Review secret storage, authentication, logs, and optional data processors.
- Help rehearse a restore without exposing backup contents.

**Human**

- Choose encrypted off-site backup storage and retention.
- Preserve the Fernet key separately.
- Perform a restore test before connecting real accounts.
- Decide which third parties may receive financial information.

**Complete when:** recovery has been tested and every processor has been
explicitly approved.

See [Backups and recovery](self-hosting.md#backups-and-recovery) and
[Security minimums](self-hosting.md#security-minimums).

## 7. Add optional services

### GitHub synchronization

The included workflow is manual-only and refuses database writes unless the
dispatch supplies both explicit confirmation and an exact reviewed commit SHA.

**Human:** create a private operational repository, enter Actions secrets
directly in GitHub, and approve each write. Designing an unattended schedule is
a separate security decision; adding a `schedule` trigger alone does not
satisfy the workflow's write gate.

### Telegram notifications

Telegram is outbound only. Summaries may contain institution or merchant names,
dates, amounts, and counts.

**Human:** decide whether Telegram is an approved processor, create the bot, and
enter its token and chat IDs directly in GitHub secrets.

### Render hosting

The included Render blueprint is for hobby and Sandbox use. Any internet-facing
deployment must require Google authentication and a non-empty owner-email
allowlist.

**Human:** create the Render service and Google OAuth client, enter secrets
directly in Render, and register the exact callback URLs.

See [Optional GitHub, Telegram, and Render services](self-hosting.md#4-optional-github-telegram-and-render-services).

## 8. Decide whether to connect live accounts

Budget Me is an experimental blueprint, not a managed financial service.

Before live use, the human must independently confirm:

- Plaid Trial or Production eligibility, product access, billing, and OAuth
  institution support;
- authenticated hosting and an owner allowlist;
- least-privilege database access and verified RLS;
- encrypted backups and a successful restore rehearsal;
- credential rotation, Plaid Item revocation, and data-deletion procedures;
- acceptable provider retention and privacy terms; and
- a plan for dependency and application updates.

The agent must not change `PLAID_ENV`, replace credentials, link live Items, or
enable recurring writes without explicit approval.

## Final handoff

The agent should provide a concise handoff containing:

- the exact installed commit;
- which providers and optional services are enabled;
- validation performed with synthetic data;
- unresolved limitations;
- backup and recovery status;
- recurring costs or quotas to monitor; and
- the next action that still requires the human.
