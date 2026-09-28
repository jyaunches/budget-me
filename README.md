<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/budget-me-gecko-logo-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/budget-me-gecko-logo-light.png">
    <img src="docs/assets/budget-me-gecko-logo-light.png"
         alt="Budget Me — Your finances. Your infrastructure."
         width="900">
  </picture>
</p>

# Budget Me

Budget Me is a self-hosted personal-finance blueprint for one person or trusted
household. It imports account data through Plaid, stores it in Supabase
PostgreSQL, and provides a Streamlit interface for transactions, budgets, debt,
forecasts, and monthly snapshots.

> **Experimental blueprint:** there is no hosted Budget Me service, stable
> release, maintenance commitment, or security-response SLA. Begin with Plaid
> Sandbox and synthetic data. Anyone connecting real accounts is responsible for
> provider terms, access control, backups, upgrades, and operational security.

## What you can do

1. **Chat with your finances** through a coding-agent harness that can work with
   this repository and its configured database.
2. **Synchronize transactions** through the guarded GitHub Actions workflow,
   which can be adapted into a nightly workflow in your own repository.
3. **Receive optional Telegram notifications** about sync results and
   uncategorized merchants.
4. **Use the Streamlit application** locally or on an authenticated remote host
   such as Render.
5. **Run a typical personal Sandbox installation within provider free tiers,**
   subject to each provider's current eligibility, quotas, and limitations.

Budget Me is not designed as a hosted service or multi-tenant platform. One
installation represents one trusted household.

## How the pieces fit together

| Component | Role |
|---|---|
| Coding-agent harness | Conversational interface for setup and reviewed finance workflows; Budget Me does not bundle a model or chat service. |
| Streamlit | Visual interface for accounts, transactions, budgets, cards, debt, forecasts, and snapshots. |
| Supabase | PostgreSQL storage for financial data, configuration, and encrypted Plaid access tokens. |
| Plaid | Account, transaction, balance, and supported liability data. |
| Fernet key | Installation-owned key that encrypts Plaid access tokens before database storage. |
| GitHub Actions | Optional remote synchronization, categorization, and notification runner. |
| Telegram | Optional outbound notifications; there is no inbound chat-to-agent integration. |
| Render and Google Cloud | Optional Streamlit hosting and Google OAuth authentication. |

## Set up a personal installation

The recommended first run is local Streamlit, a dedicated Supabase project,
Plaid Sandbox, and manual synchronization.

Ask your coding-agent harness:

> Use `docs/SETUP.md` to guide me through a new Budget Me Sandbox
> installation. Explain each step, distinguish what you can do from what I must
> do, pause before writes or provider changes, and never ask me to paste secrets
> into chat.

Start with the [agent-guided setup](docs/SETUP.md). It links to the detailed
[self-hosting reference](docs/self-hosting.md) for commands and provider
configuration.

## What the human must do

### On the local machine

- Approve the repository revision and installation directory.
- Enter secrets directly into the ignored `.env` file.
- Keep the Fernet key and database backups in protected storage.
- Review financial categories, account relationships, and month-close choices.

### In Supabase

- Create a dedicated project and choose its region.
- Save the database password and copy the Session pooler connection string.
- Authorize initial database setup and future schema upgrades.
- Plan backups before storing live financial data.

### In Plaid

- Create a Plaid team and accept its terms.
- Enable Transactions and Liabilities for the complete application experience.
- Enter the client ID and environment-specific secret privately.
- Personally complete Link, OAuth, consent, re-consent, and relinking.

### In GitHub, optionally

- Use a private fork or repository for any installation containing secrets or
  operational configuration.
- Add Actions secrets directly in repository settings.
- Approve database writes and any scheduled synchronization design.

### In Telegram, optionally

- Decide whether Telegram may receive financial notification details.
- Create the bot and enter its token and chat IDs directly in GitHub secrets.

### In Render and Google Cloud, optionally

- Create the Render service and Google OAuth client.
- Enter secrets directly in Render and maintain a non-empty email allowlist.
- Treat Render Free as hobby/Sandbox hosting rather than production hosting.

## Cost expectations

Provider terms change, so check them before setup.

- Plaid Sandbox is free and uses synthetic data.
- Eligible new Plaid teams in the United States and Canada may qualify for a
  free Trial with up to 10 lifetime Production Items. Removing an Item does not
  restore its slot.
- Supabase currently provides two active Free projects with a 500 MB database
  quota per project; inactive projects may pause.
- Standard GitHub-hosted Actions runners are free for public repositories.
- Render offers a Free web-service tier, but it sleeps when idle, uses an
  ephemeral filesystem, has usage limits, and is explicitly not intended for
  production applications.
- Telegram bot messaging is generally free, while model usage, backup storage,
  and production-grade hosting may cost money.

See [free-tier caveats](docs/self-hosting.md#free-tier-caveats) and verify the
linked provider documentation for current limits.

## Documentation

- [Agent-guided setup](docs/SETUP.md) — a human-and-agent onboarding sequence.
- [Self-hosting reference](docs/self-hosting.md) — exact commands, optional
  services, backups, security boundaries, and troubleshooting.
- [Contributing](CONTRIBUTING.md) — development and contribution expectations.
- [Security](SECURITY.md) — maintenance status, reporting guidance, and
  sensitive-data rules.

## Development

```bash
make dev
make lint
make test
make audit
```

Database and Plaid Sandbox integration suites require separate explicit opt-ins
and disposable databases. Never point tests at a household or persistent
database.

## License

Budget Me is licensed under the [Apache License 2.0](LICENSE). Unless otherwise
noted, that license covers the source, documentation, and logo assets in this
repository. The gecko artwork was generated with ChatGPT and selected for this
project; no claim is made that generative output is exclusive or eligible for
copyright protection in every jurisdiction.
