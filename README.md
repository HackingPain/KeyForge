# KeyForge

Self-hosted, open-source vault and (future) issuer for third-party API credentials.

## What is KeyForge

KeyForge is a self-hosted credential management platform for the API keys, tokens, and secrets your team uses to talk to third-party services (GitHub, AWS, Stripe, OpenAI, and so on). It stores credentials with envelope and field-level encryption at rest, signs every change into a tamper-evident audit log, supports rotation policies and breach detection, and exposes a REST API, Python SDK, CLI, and React dashboard so credentials can be used without humans copy-pasting them around. Comparable projects in the same space include HashiCorp Vault, Doppler, and Infisical.

## Status

KeyForge is **alpha**. The vault path (store a credential you already have, retrieve it, rotate it, audit access) works end to end. The issuer path (click a button, KeyForge mints a fresh credential against a provider for you) is on the roadmap and not yet shipped. If you are evaluating KeyForge as a "non-technical user gets a working API key without ever seeing the word PAT" tool, that flow is Tier 2 work; see [tasks/todo.md](tasks/todo.md) for the authoritative plan and current status.

Backend version is v5.0. Expect breaking changes between minor versions until a 1.0 release.

## Feature highlights

- Credential CRUD with Fernet symmetric encryption at rest
- Envelope encryption with a pluggable KMS abstraction (DEK wrapped by KEK)
- Field-level encryption for sensitive credential metadata
- TOTP-based multi-factor authentication
- Append-only audit log with hash-chain integrity verification
- Rotation policies, expiration policies, and IP allowlist policy engines
- Basic teams, groups, and role-based access
- Python SDK (`tools/sdk/client.py`) and command-line tool (`tools/cli.py`)
- FastAPI REST API with per-feature routers
- React 19 + Tailwind dashboard
- Prometheus metrics endpoint at `/metrics`
- Outbound webhooks signed with HMAC
- Docker Compose for local orchestration

## 5-minute quickstart

```
git clone https://github.com/DarkHorse-InfoSec/KeyForge.git
cd KeyForge
python tools/cli.py init
docker compose up --build
open http://localhost:3000
```

`python tools/cli.py init` generates a fresh Fernet `ENCRYPTION_KEY` and a 64-byte URL-safe `JWT_SECRET`, then writes them to `backend/.env` along with `MONGO_URL` and `DB_NAME=keyforge`. It refuses to overwrite existing keys without `--force`, because rotating the encryption key destroys all existing encrypted data. This command is being added on the `fix/tier1-bootstrap` branch alongside this README; if you are on an older commit you will need to set those two variables by hand.

After `docker compose up`, the backend is on port 8001, the frontend is on port 3000, and MongoDB runs internally to the compose network. Register a user from the dashboard to get started.

For the credential-issuer features (Connect GitHub, mint AWS STS) to work end to end against real providers, an operator must register a GitHub App on the org and wire AWS credentials into the deployment env. The combined runbook is in [docs/operator-setup.md](docs/operator-setup.md). A standalone, self-contained AWS-only walkthrough lives at [docs/aws-setup.md](docs/aws-setup.md).

## Local development without Docker

For bare-metal hacking, the short version is:

```
# Backend (from repo root)
pip install -r requirements.txt
uvicorn backend.server:app --reload --port 8001

# Frontend (from frontend/)
yarn install
yarn start
```

The full toolchain (formatters, linters, test commands, e2e setup, env variables) is documented in [CLAUDE.md](CLAUDE.md). Refer to that file rather than duplicating commands here, so there is one source of truth.

## Architecture at a glance

- **Router-per-feature.** Every feature lives in its own `backend/routes/<feature>.py`, paired with a React component in `frontend/src/components/`.
- **Models split by domain.** `backend/models.py` holds the core; `backend/models_<domain>.py` files cover audit, kms, teams, envelope, field encryption, lifecycle, policy, analytics, backup, proxy, security, and extended models.
- **Layered encryption.** Field-level encryption wraps individual credential fields. Envelope encryption wraps DEKs with a KEK from the configured KMS. Plaintext credentials never reach Mongo.
- **Audit log is a hash chain.** Records are append-only and tamper-evident. Integrity is verified by `routes/audit_integrity.py`.
- **Migrations run via FastAPI lifespan.** New migrations register themselves in `backend/migrations/versions.py` and execute at startup. No ad-hoc Mongo init scripts.
- **Middleware order is load-bearing.** Rate limiting, sanitization, security headers, monitoring, and error handlers are wired in `backend/server.py` in a deliberate order. Add new middleware there.

## Roadmap

The full plan lives in [tasks/todo.md](tasks/todo.md). The high-level tiers:

- **Tier 1: Make it work at all.**
  Hardening pass: fix bootstrap papercuts, add the `keyforge init` keygen, ship LICENSE and CONTRIBUTING, get CI green on a fresh clone.
- **Tier 2: Become an issuer.**
  Add a `CredentialIssuer` interface, ship a GitHub App issuer (mint fine-grained PATs from a button click), an AWS STS issuer (short-lived assumed-role credentials with real auto-rotation), and JSON-driven guided walkthroughs for providers without mint APIs (Stripe, OpenAI, and similar).
- **Tier 3: First-run wizard and jargon stripping.**
  Replace the empty dashboard for new users with a guided "connect a provider, generate your first credential" flow, hide advanced features behind a Basic/Advanced toggle, and wrap every jargon term (TOTP, KMS, DEK, KEK, PAT, CIDR, and so on) in a tooltip component that explains it in plain language.
- **Tier 4: Finish or remove the stubs.**
  Each placeholder route (breach detection, cost estimation, the VS Code extension, the Kubernetes and Terraform integrations) either gets a real implementation or is deleted. CI gains coverage floors and a Docker smoke job.

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) for branch naming, commit message format, the test policy, and code style rules before opening a pull request.

## Security

KeyForge handles credentials at rest, so security reports are treated as high priority. Please do not file public issues for vulnerabilities. See SECURITY.md if present, or open a private security advisory through GitHub's security tab on this repository.

## License

KeyForge is released under the Apache License 2.0. See [LICENSE](LICENSE) for the full text. The Apache 2.0 license carries an explicit patent grant and trademark protection clause that the MIT License lacks.
