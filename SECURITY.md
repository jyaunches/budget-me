# Security policy

## Maintenance status

Budget Me is an experimental blueprint maintained on a best-effort basis. It has
no stable supported release, guaranteed response time, fix deadline, or
security-response SLA.

| Version | Support |
| --- | --- |
| Current `main` | Best effort only |
| Older commits, forks, and deployments | Not supported |

Self-hosters are responsible for reviewing updates, dependencies, provider
terms, access control, backups, and incident response for their installation.

## Reporting a security concern

Budget Me does not currently operate a monitored private security mailbox.

- For a concern that can be described safely without exploit details, secrets,
  or household data, open a GitHub issue.
- If the repository's **Security** tab offers private vulnerability reporting,
  use that for sensitive technical details.
- If no private reporting option is available, do not publish weaponizable
  details or sensitive data. A private response channel and coordinated
  disclosure cannot be promised.

A report should use synthetic examples and identify the affected commit, file,
workflow, or configuration. Never include credentials, database URLs, Plaid
tokens, encryption keys, real transactions, account details, statements,
screenshots, database dumps, or secret-bearing logs.

For a vulnerability in Plaid, Supabase, Render, Streamlit, GitHub, Telegram, or
another provider rather than Budget Me code, also use that provider's reporting
process.

## High-impact areas

Treat these as potentially critical:

- unauthorized access to financial records;
- exposure or decryption of a Plaid access token;
- missing or bypassable RLS on a public-schema table;
- authentication that does not enforce the owner allowlist;
- SQL injection or arbitrary database writes;
- prompt injection reaching an agent with database, GitHub, Plaid, messaging,
  or shell credentials;
- public events triggering privileged workflows;
- financial details written to issues, Actions logs, artifacts, screenshots,
  telemetry, or notifications;
- insecure backups or credential rotation; and
- dependency or container compromise reaching stored data.

## Financial-data model

Budget Me may store:

- encrypted Plaid access tokens;
- account identifiers, masks, institution names, and balances;
- transactions, merchants, dates, amounts, categories, and raw Plaid objects;
- credit-card APRs, loan balances, payment dates, and forecasts;
- budgets, reimbursements, categorization rules, and free-text notes.

Encrypting Plaid tokens does not make the remaining database non-sensitive. A
database credential, backup, authenticated application session, or privileged
agent may reveal extensive household information.

The application connects directly to PostgreSQL. Depending on the role, that
connection can bypass RLS. RLS protects the Supabase API surface but is not a
substitute for least-privilege database credentials and application
authorization.

## Security baseline for self-hosters

- Begin with Plaid Sandbox and synthetic data.
- Keep `.env`, Streamlit secrets, dumps, screenshots, statements, exports,
  and generated JSON out of Git.
- Use a dedicated Supabase project and least-privilege runtime role.
- Verify RLS on every public-schema financial table.
- Require hosted authentication and a non-empty owner allowlist.
- Bind unauthenticated local services to loopback.
- Keep transaction detail out of CI, issues, and agent logs.
- Review every external processor before supplying financial data.
- Encrypt backups, preserve the Fernet key separately, and test restoration.
- Document Plaid Item revocation and complete data deletion.
- Keep privileged agent and messaging workflows disabled by default.
- Regularly update and audit locked dependencies.

## If exposure is suspected

1. Stop the affected service or workflow.
2. Preserve only the minimum redacted evidence.
3. Rotate affected credentials.
4. Revoke or relink Plaid Items if a token may be exposed.
5. Review provider audit logs.
6. Remove public artifacts that contain sensitive data.
7. Assess backups, forks, caches, and Git history.
8. Document the remediation without republishing the sensitive material.

Changing `APP_TOKEN_ENC_KEY` without re-encrypting stored tokens makes them
unreadable. Plan key rotation as a migration or revoke and relink the affected
Items.

See [Self-hosting Budget Me](docs/self-hosting.md) for installation safeguards.
