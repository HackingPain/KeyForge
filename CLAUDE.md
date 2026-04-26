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
├── tools/                   Python SDK (sdk/client.py), VS Code extension, docker_integration.py
├── Dockerfile.backend       Python 3.11-slim + uvicorn
├── Dockerfile.frontend      Node 20 build, then nginx:alpine
├── docker-compose.yml       mongodb + backend + frontend
├── requirements.txt         Backend deps (root, NOT backend/requirements.txt, see Gotchas)
└── .github/workflows/       deploy.yml (tag-triggered, currently a stub)
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

```bash
# backend/.env
MONGO_URL=mongodb://localhost:27017     # or mongodb://mongodb:27017 in compose
DB_NAME=keyforge                        # current committed value is "test_database", see Gotchas

# Required at runtime but NOT in committed .env:
ENCRYPTION_KEY=                         # Fernet/AES key for field + envelope encryption
JWT_SECRET=                             # JWT signing secret for auth

# frontend/.env
REACT_APP_BACKEND_URL=http://localhost:8001
WDS_SOCKET_PORT=443
```

## Architecture Notes

- **Router-per-feature.** Every feature area gets its own `backend/routes/<feature>.py` and a matching React component in `frontend/src/components/`. When adding a feature, follow that pairing instead of fattening an existing file.
- **Models split by domain.** `backend/models.py` holds the core; `backend/models_<domain>.py` (audit, kms, teams, envelope, field_encryption, lifecycle, policy, analytics, backup, proxy, security, extended) holds domain-specific Pydantic models. Pick the right one rather than dumping everything into `models.py`.
- **Migrations run at startup.** `backend/migrations/runner.py` is invoked from the FastAPI lifespan; new migrations register themselves in `backend/migrations/versions/__init__.py`. Do not write ad-hoc Mongo init scripts.
- **Encryption is layered.** Field-level encryption (`backend/encryption/`, `routes/field_encryption.py`) wraps individual credential fields; envelope encryption (`routes/envelope_encryption.py`) wraps DEKs with a KEK from the configured KMS (`routes/kms_admin.py`). Never bypass these to write raw plaintext to Mongo.
- **Audit integrity is a hash chain.** `backend/audit/` and `routes/audit_integrity.py` implement tamper-evident logging. Treat the chain as append-only; do not write code that mutates or deletes audit records.
- **Middleware order matters.** `server.py` wires rate_limiter, sanitizer, security_headers, monitoring, and error handlers. Add new middleware in the same file and respect existing order.

## Coding Standards (project-specific)

- Backend formatter line length is 120 (see flake8 invocation), not 88. Use `python -m black backend/` (it picks up project config) and don't hand-wrap to 88.
- Frontend uses CRACO, not vanilla react-scripts. Always invoke `yarn` scripts or `npx craco`, never `npx react-scripts` directly, or you bypass overrides.
- React 19 + react-router-dom v7. Use the v7 data-router APIs in new code; do not pattern-match against older v5/v6 examples.
- Tests live in `tests/` (backend) and `frontend/src/__tests__/` (frontend). Mirror existing naming: `test_<feature>.py` and `<Component>.test.js`.

## Known Issues & Gotchas

- [ ] **`Dockerfile.backend` references `backend/requirements.txt`** but the actual file is at the repo root (`requirements.txt`). The image build will fail until either the Dockerfile is fixed or a copy is placed under `backend/`. Check before assuming `docker compose up` works clean.
- [ ] **`backend/.env` ships with `DB_NAME="test_database"`.** That looks like a leftover from scaffolding. For real use, set it to `keyforge` (which is what `docker-compose.yml` expects). Don't propagate `test_database` into new code or docs.
- [ ] **`ENCRYPTION_KEY` and `JWT_SECRET` are required at runtime but absent from `backend/.env`.** Anything that touches credential write/read or auth will crash without them. Make sure they're exported in the shell or compose env before starting the backend.
- [ ] **`.github/workflows/deploy.yml` is a stub.** The actual `docker build` lines are commented out; the job only echoes and creates a GitHub release. Don't assume CI publishes images.
- [ ] **`frontend/.env` sets `WDS_SOCKET_PORT=443`.** This is for an HTTPS reverse-proxied dev setup; on a plain `localhost:3000` dev session it's harmless but if hot-reload misbehaves, that's the first thing to check.
- [ ] **No top-level README.** New contributors will need to be pointed at this CLAUDE.md or a README needs to be written. (Don't create one unless asked, per global rules.)

## External Services & Integrations

| Service       | Purpose                          | Auth          | Notes                                                |
| ------------- | -------------------------------- | ------------- | ---------------------------------------------------- |
| MongoDB 7     | Primary datastore                | Connection URI | Local via docker-compose; not exposed to host by default |
| KMS (pluggable) | Wraps DEKs for envelope encryption | Configurable | See `backend/routes/kms_admin.py` for supported backends |
| Webhooks      | Outbound notifications           | HMAC          | `backend/routes/webhooks.py`                         |
| Prometheus    | Metrics scraping                 | None          | `backend/routes/metrics.py` exposes `/metrics`       |

## Session Startup Checklist

- [ ] Read `tasks/lessons.md` and `tasks/todo.md` if present (neither exists yet at time of writing).
- [ ] Confirm whether the change touches credential storage, encryption, or audit; if so, the safety/security and no-shortcuts principles in the global CLAUDE.md apply with full force.
- [ ] Check `docker-compose.yml` and `backend/.env` are consistent before any local run.
