# CLAUDE.md, KeyForge

> Project-specific guidance. Global workflow rules, git conventions, and core principles live in `~/.claude/CLAUDE.md`; do not re-state them here.

## Project Overview

**Project:** KeyForge
**Description:** Self-hosted, open-source API credential management platform. Vault for third-party API keys with heavy emphasis on rotation, breach detection, envelope/field encryption, audit-log integrity, and compliance reporting. Comparable space: HashiCorp Vault, Doppler, Infisical.
**Stack:** FastAPI (Python 3.11) + MongoDB (Motor async driver) on the backend; React 19 + CRA/CRACO + Tailwind on the frontend; Docker Compose for local orchestration; Nginx serves the built frontend.
**Owner:** DarkHorse Infosec (org). Repo: `DarkHorse-InfoSec/KeyForge`. Original author and maintainer: Domenic Laurenzi. Open source under Apache 2.0.
**Backend version:** v5.0 (see `backend/server.py` docstring).

## Directory Structure

```
KeyForge/
├── backend/                 FastAPI app (server.py is the entrypoint)
│   ├── server.py            App factory, router registration, middleware wiring
│   ├── config.py            Mongo client, env loading, logger
│   ├── models*.py           Pydantic models, split by domain (audit, kms, teams, etc.)
│   ├── routes/              ~30 routers, one per feature area (auth, credentials, rotation, ...)
│   ├── middleware/          rate_limiter, sanitizer, security_headers, monitoring, error_handler
│   ├── migrations/          Versioned schema migrations, run at startup via runner.py
│   ├── encryption/          Field + envelope encryption primitives
│   ├── key_types/           Per-provider credential schemas
│   ├── policies/            Expiration, rotation, IP allowlist policy engines
│   ├── audit/               Audit log + integrity verification (hash chain)
│   ├── backup/              Backup/restore routines
│   ├── scanners.py          Secret-scanning patterns
│   └── .env                 MONGO_URL, DB_NAME (gitignored)
├── frontend/                React 19 SPA (CRA via CRACO + Tailwind)
│   ├── src/components/      One component per backend feature area
│   ├── src/api.js           Axios client, points at REACT_APP_BACKEND_URL
│   └── nginx.conf           Production server config
├── tests/                   Backend pytest suite (test_*.py per domain)
├── e2e/                     Playwright end-to-end tests (auth, dashboard)
├── integrations/            Optional integrations: kubernetes (CRD+RBAC), terraform, git-hooks
├── tools/                   Python SDK (sdk/client.py), CLI (cli.py), docker_integration.py
├── experimental/            Promotion-pending: vscode_extension, kubernetes operator, terraform provider
├── docs/                    operator-setup.md (GitHub App + AWS runbook)
├── Dockerfile.backend       Python 3.11-slim + uvicorn
├── Dockerfile.frontend      Node 20 build, then nginx:alpine
├── docker-compose.yml       mongodb + backend + frontend; env_file: backend/.env (required: false)
├── requirements.txt         Backend deps (single canonical file at repo root after Tier 1.4)
└── .github/workflows/       ci.yml (7 jobs incl. e2e + docker-smoke), deploy.yml (real GHCR push)
```

## Environment & Commands

### Backend (run from repo root)

```bash
pip install -r requirements.txt
uvicorn backend.server:app --reload --port 8001       # dev
python -m pytest tests/ -v --tb=short                 # tests
python -m black backend/                              # format
python -m isort backend/                              # imports
python -m flake8 backend/ --max-line-length=120 --ignore=E501,W503
```

### Frontend (run from `frontend/`)

```bash
yarn install            # package manager is yarn (see frontend/package.json)
yarn start              # craco start, dev server on :3000
yarn build              # production build into frontend/build
yarn test               # craco test (Jest + RTL)
npx eslint src/         # lint
```

### E2E (run from `e2e/`)

```bash
npm install
npx playwright test
```

### Full stack via Docker

```bash
docker compose up --build
# backend on :8001, frontend on :3000, mongodb internal-only
```

### Required env vars

`backend/.env` is gitignored. The fastest way to populate it is `python tools/cli.py init` from the repo root: that generates a Fernet `ENCRYPTION_KEY`, a 64-byte URL-safe `JWT_SECRET`, and writes `MONGO_URL` + `DB_NAME=keyforge`. `backend/.env.example` documents every key the backend reads. The minimum set:

```bash
# backend/.env (gitignored; tools/cli.py init populates the first four)
MONGO_URL=mongodb://localhost:27017      # bare-metal; compose overrides to mongodb://mongodb:27017
DB_NAME=keyforge
ENCRYPTION_KEY=<44-char Fernet key>
JWT_SECRET=<86-char URL-safe secret>

# Optional: HTTP localhost dev needs the auth cookie without TLS
KEYFORGE_COOKIE_SECURE=false

# Tier 2.2 GitHub issuer (see docs/operator-setup.md Part 1)
GITHUB_APP_ID=
GITHUB_APP_PRIVATE_KEY=                  # PEM contents OR filesystem path
GITHUB_APP_CLIENT_ID=
GITHUB_APP_CLIENT_SECRET=
GITHUB_APP_SLUG=
GITHUB_APP_INSTALL_REDIRECT_URL=http://localhost:8001/api/issuers/github/callback
KEYFORGE_FRONTEND_URL=http://localhost:3000

# Tier 2.3 AWS issuer (see docs/operator-setup.md Part 2)
AWS_REGION=us-east-1
KEYFORGE_AWS_ACCOUNT_ID=
# Plus AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY OR an instance role

# frontend/.env
REACT_APP_BACKEND_URL=http://localhost:8001
WDS_SOCKET_PORT=443
```

## Architecture Notes

- **Router-per-feature.** Every feature area gets its own `backend/routes/<feature>.py` and a matching React component in `frontend/src/components/`. When adding a feature, follow that pairing instead of fattening an existing file.
- **Models split by domain.** `backend/models.py` holds the core; `backend/models_<domain>.py` (audit, kms, teams, envelope, field_encryption, lifecycle, policy, analytics, backup, proxy, security, extended) holds domain-specific Pydantic models. Pick the right one rather than dumping everything into `models.py`.
- **Migrations run at startup.** `backend/migrations/runner.py` is invoked from the FastAPI lifespan; new migrations register themselves in `backend/migrations/versions.py` (single file, NOT a versions/ directory). Do not write ad-hoc Mongo init scripts.
- **Encryption is layered.** Field-level encryption (`backend/encryption/`, `routes/field_encryption.py`) wraps individual credential fields; envelope encryption (`routes/envelope_encryption.py`) wraps DEKs with a KEK from the configured KMS (`routes/kms_admin.py`). Never bypass these to write raw plaintext to Mongo.
- **Audit integrity is a hash chain.** `backend/audit/` and `routes/audit_integrity.py` implement tamper-evident logging. Treat the chain as append-only; do not write code that mutates or deletes audit records.
- **Middleware order matters.** `server.py` wires SecurityHeaders -> Monitoring -> RateLimit -> CSRF -> Sanitization (outermost first). Add new middleware in the same file and respect existing order.
- **Auth is httpOnly cookie + CSRF double-submit (Tier 1.7).** `keyforge_token` is HttpOnly + Secure (gated on `KEYFORGE_COOKIE_SECURE`); `keyforge_csrf` is JS-readable and echoed in `X-CSRF-Token` on mutating `/api/*` requests. Bearer-token auth still works for the CLI/SDK and bypasses CSRF.
- **Issuer abstraction (Tier 2).** `backend/issuers/base.py` defines the `CredentialIssuer` ABC plus `IssuedCredential` model; `backend/issuers/github.py` and `backend/issuers/aws.py` implement it. Routes register themselves at module import time via `register_issuer(name, instance)`. The four methods (`start_oauth`, `complete_oauth`, `mint_scoped_credential`, `revoke`) raise `IssuerNotSupported` by default; concrete subclasses override only the ones they list in their `supports: ClassVar[Set[str]]` attribute. Never instantiate an issuer directly in routes; use `get_issuer(name)`.

## Coding Standards (project-specific)

- Backend formatter line length is 120 (see flake8 invocation), not 88. Use `python -m black backend/` (it picks up project config) and don't hand-wrap to 88.
- Frontend uses CRACO, not vanilla react-scripts. Always invoke `yarn` scripts or `npx craco`, never `npx react-scripts` directly, or you bypass overrides.
- React 19 + react-router-dom v7. Use the v7 data-router APIs in new code; do not pattern-match against older v5/v6 examples.
- Tests live in `tests/` (backend) and `frontend/src/__tests__/` (frontend). Mirror existing naming: `test_<feature>.py` and `<Component>.test.js`.

## Known Issues & Gotchas

- [ ] **`frontend/.env` sets `WDS_SOCKET_PORT=443`.** This is for an HTTPS reverse-proxied dev setup; on a plain `localhost:3000` dev session it's harmless but if hot-reload misbehaves, that's the first thing to check.
- [ ] **`docker compose up` requires `backend/.env` to exist OR shell-exported `ENCRYPTION_KEY` + `JWT_SECRET`.** The compose file uses `env_file: backend/.env (required: false)`; if the file is missing AND those two vars are not in the shell, the container boots with empty secrets and crashes with "Fernet key must be 32 url-safe base64-encoded bytes". CI generates the file inline; locally, run `python tools/cli.py init` first.
- [ ] **`tests/_test_helpers.py` overrides `ENCRYPTION_KEY` and `JWT_SECRET`** at import time. Pytest does not see the values from `backend/.env` or the shell; the test helper hardcodes valid keys for determinism. If you write a new test that constructs a Fernet directly, do NOT also try to override these; the helper is the single source of truth.
- [ ] **CI's `e2e/tests/auth.spec.js` and `e2e/tests/dashboard.spec.js` are `test.describe.skip`'d** until the cookie-auth rewrite (task #11). The job runs but those suites are skipped. Other e2e tests still run.
- [ ] **Three starlette CVEs are documented in `SECURITY_FINDINGS.md`** because `fastapi==0.110.1` hard-pins `starlette>=0.37.2,<0.38.0`. Upgrading both is a coordinated change; do not silently bump.

### Resolved (kept here as a paper trail; do NOT re-introduce)

- ~~`Dockerfile.backend` references `backend/requirements.txt`~~ - resolved Tier 1.4 (single canonical `requirements.txt` at repo root).
- ~~`backend/.env` ships with `DB_NAME="test_database"`~~ - resolved Tier 1.2 (`tools/cli.py init` writes `keyforge`).
- ~~`ENCRYPTION_KEY` / `JWT_SECRET` absent from committed env~~ - resolved Tier 1.2 (`tools/cli.py init` generates real values; `backend/.env.example` documents them).
- ~~`.github/workflows/deploy.yml` is a stub~~ - resolved Tier 1.6 (real GHCR push on tag).
- ~~No top-level README~~ - resolved Tier 1.5 (alpha-honest README ships at repo root).

## External Services & Integrations

| Service          | Purpose                              | Auth                  | Notes                                                                |
| ---------------- | ------------------------------------ | --------------------- | -------------------------------------------------------------------- |
| MongoDB 7        | Primary datastore                    | Connection URI        | Local via docker-compose; not exposed to host by default             |
| KMS (pluggable)  | Wraps DEKs for envelope encryption   | Configurable          | See `backend/routes/kms_admin.py` for supported backends             |
| Webhooks         | Outbound notifications               | HMAC                  | `backend/routes/webhooks.py`                                         |
| Prometheus       | Metrics scraping                     | None                  | `backend/routes/metrics.py` exposes `/metrics`                       |
| GitHub App       | Tier 2.2 issuer (mint fine-grained PATs) | App JWT + installation token | Operator setup: `docs/operator-setup.md` Part 1                  |
| AWS STS          | Tier 2.3 issuer (assume-role mint)   | boto3 default chain   | Operator setup: `docs/operator-setup.md` Part 2                      |
| GHCR             | Container image registry              | GITHUB_TOKEN          | `ghcr.io/darkhorse-infosec/keyforge/{backend,frontend}` on tag push  |

## Session Startup Checklist

- [ ] Read `tasks/lessons.md` (corrections from prior sessions) and `tasks/todo.md` (the four-tier plan; all tiers code-complete as of 2026-04-26, but the plan still tracks operator follow-ups for Tier 2 live acceptance).
- [ ] If touching credential storage, encryption, the audit hash chain, or the auth path: the safety/security and no-shortcuts principles in the global `~/.claude/CLAUDE.md` apply with full force.
- [ ] Before running locally: confirm `backend/.env` exists (`python tools/cli.py init` creates it) and the `GITHUB_APP_*` / `AWS_*` env vars are set if you intend to exercise the issuer flows. `docs/operator-setup.md` is the runbook.
- [ ] Verify CI baselines before opening a PR: backend pytest >= 443 passing, frontend jest >= 90 passing, `bandit -r backend/ -ll --skip B101` exits 0.
