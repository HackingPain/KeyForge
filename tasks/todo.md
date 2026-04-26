# KeyForge Implementation Plan

> Authoritative plan, written 2026-04-26, derived from the full audit. Cross-session source of truth. Read this at the start of every KeyForge session before touching code. Mark items complete as they land, not at session end. Update the **Status** line of each section as work moves.

## North Star

KeyForge today is a credential vault (stores keys you already have). The goal is to make it a credential **issuer** (clicks a button, gets a credential) usable by people who don't know what an API key is. Every change is judged against: **does this help a non-technical user get and use a credential without ever seeing the word PAT?**

## Working agreement

- Use subagents (teams) for any chunk of work larger than a single-file edit. Parallelise independent slices.
- Trust-but-verify: after a subagent reports done, read the diff before checking the box.
- Update this file in-line as work lands. No "done in another doc" notes.
- Don't open Tier N+1 work until Tier N is at least 80% landed and verified.
- No `Co-Authored-By:` trailers on commits. No `--no-verify`. Feature branches only.
- HIPAA / safety-security-first principles in `~/.claude/CLAUDE.md` apply with full force whenever touching encryption, audit log, or auth code.

---

## Tier 1: Make it Work At All
**Goal:** Fresh `git clone` + one command = running app with persistent data and green CI.
**Status:** In progress. 1.1, 1.2, 1.5, 1.6 merged to `main` (commits 252117f / 01ac9ed / de8533e). 1.3 done on `fix/tier1-rest`; 1.4 and 1.7 in flight (parallel subagents).
**Estimate:** 1-2 days serial; ~1 day with subagents.

### 1.1 Fix FastAPI router incompatibility (BLOCKING for CI)
- [x] Identify every `APIRouter(... on_startup=...)` (or `on_shutdown=`) in `backend/routes/` and `backend/`.
  - Result: zero matches. The audit memo's user-code hypothesis was wrong. Root cause is a dep version mismatch: FastAPI 0.110.1 internally calls Starlette `Router(... on_startup=...)`, which Starlette 1.0.0 (released to pypi after the project was last green) no longer accepts.
- [x] Replace with FastAPI lifespan handlers wired into `backend/server.py` `lifespan` function (already present, lines ~108-118).
  - Already done: `lifespan` is wired correctly. No action needed in user code.
- [x] Pin compatible versions in both `requirements.txt` and `backend/requirements.txt`: `fastapi==0.110.1`, `starlette==0.36.3`. (Tier 1.4 will merge the two requirements files.)
- [x] Verify: `python -m pytest tests/ --collect-only -q` exits 0 with 0 collection errors. Result: 370 tests collected, 0 errors.
- [x] Verify: full `python -m pytest tests/ -v` runs. Result: 370 passed locally.
- [ ] Acceptance: `.github/workflows/ci.yml` `backend-test` job goes green on a PR. (Pending PR.)

### 1.2 Add `keyforge init` keygen command
- [x] Extend `tools/cli.py` with a new `init` subcommand.
- [x] Generates a Fernet key for `ENCRYPTION_KEY` (44 chars urlsafe-b64 of 32 random bytes) and a 64-byte URL-safe secret for `JWT_SECRET` (`secrets.token_urlsafe(64)`, 86 chars).
- [x] Writes/updates `backend/.env` (creating it if missing) with both keys plus `MONGO_URL` and `DB_NAME=keyforge` (only overwrites `DB_NAME` when it is empty or the legacy `test_database`).
- [x] Refuses to overwrite existing keys without `--force`. Prints a banner warning that overwriting `ENCRYPTION_KEY` makes all encrypted credentials permanently unreadable.
- [x] Acceptance: `python tools/cli.py init` on a fresh clone produces a working `.env`. Backend will no longer hit the ephemeral-key path because both env vars are set.

### 1.3 Fix env defaults and split-brain
- [x] `backend/.env` `DB_NAME=test_database` is auto-upgraded to `keyforge` by `tools/cli.py init` (Tier 1.2). The local file itself is gitignored and not committed.
- [x] Project policy: `backend/.env` stays gitignored. Shipped `backend/.env.example` as the template. `.gitignore` already had `!.env.example` which the negation rule applies to nested paths too (verified via `git check-ignore -v`); no change needed there.
- [x] Acceptance: `docker compose up` and bare-metal `uvicorn` both read `DB_NAME=keyforge` (compose hardcodes it; bare-metal reads `backend/.env` written by `init`).

### 1.4 Fix Dockerfile path issues
- [x] Reconciled to ONE canonical `requirements.txt` at repo root. Deleted `backend/requirements.txt`. Merged `boto3` (lazy-imported by the AWS KMS provider) into root; dropped 8 unused deps that were never imported under `backend/` (requests-oauthlib, email-validator, pyjwt, tzdata, pandas, numpy, jq, typer).
- [x] `Dockerfile.backend:6` now `COPY requirements.txt .` (no `backend/` prefix).
- [x] `Dockerfile.frontend` left alone; the new `.dockerignore` excludes `frontend/node_modules` so the host tree no longer clobbers the image-side install during `COPY frontend/ ./`.
- [x] Added `.dockerignore` at repo root: 35 patterns across 13 categories (node_modules, py-bytecode, venvs, .git, tests, e2e, frontend/build, env files, docs, tasks/, CI/editor configs, OS metadata, logs, coverage/build artifacts).
- [x] Updated `.github/workflows/ci.yml` to use root `requirements.txt` (3 path swaps in backend-lint, backend-test, security-scan).
- [ ] Acceptance: `docker compose build --no-cache` succeeds and images < 1.2 GB combined. (Not yet run; will validate when first PR triggers CI or first manual build.)

### 1.5 Repo hygiene: README, LICENSE, CONTRIBUTING
- [x] Write `README.md` at repo root (replaced the prior marketing-style README; the audit memo's claim that no README existed was wrong, the prior file existed but did not reflect actual project state). New README is alpha-honest, links to `tasks/todo.md` for the issuer roadmap, no AI-attribution footer.
- [x] Add `LICENSE` (MIT, copyright 2026 Domenic Laurenzi).
- [x] Add `CONTRIBUTING.md` covering branch naming, commit format (with the verbatim no-co-author / no-Claude-footer rule), test policy, code style.
- [ ] Acceptance: a stranger can land on the GitHub page and run the app within 5 minutes without reading source. (Verified via the README quickstart referencing `tools/cli.py init` + `docker compose up`. End-to-end manual test pending Tier 1.4.)

### 1.6 Fix the deploy workflow
- [x] `.github/workflows/deploy.yml` rewritten: real `docker/login-action@v3` to GHCR, `docker/build-push-action@v6` for both backend and frontend images (tagged `:${ref_name}` and `:latest`), `permissions: contents: write, packages: write`, then `softprops/action-gh-release@v2`. No commented-out placeholder lines.
- [ ] Acceptance: tagging `v0.x.y` actually publishes images to `ghcr.io/HackingPain/KeyForge/{backend,frontend}`. (Verified by YAML-parsing only; first real tag will exercise the workflow.)

### 1.7 Move JWT to httpOnly cookie (security + Tier 1 because it's small)
- [x] Backend `routes/auth.py`: login now sets `Set-Cookie: keyforge_token=...; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=3600`. `Secure` flag gated on `KEYFORGE_COOKIE_SECURE` env var (default true; set false for HTTP dev). Body still returns `{access_token, token_type}` for CLI/SDK. Added `POST /api/auth/logout` that clears the cookie.
- [x] Extended `get_current_user` in `backend/security.py` to read the JWT from the `keyforge_token` cookie first, falling back to the `Authorization: Bearer ...` header. Added `get_current_token` dependency for routes that need the raw JWT string (sessions.py uses it to hash-and-compare). `oauth2_scheme` kept exported for OpenAPI compat but no longer wired into route deps.
- [x] Frontend `src/api.js`: dropped all `localStorage.getItem('keyforge_token')` reads/writes. `withCredentials: true` on the axios instance. New request interceptor reads the `keyforge_csrf` cookie and sets `X-CSRF-Token` on POST/PUT/PATCH/DELETE. 401 interceptor clears server cookie via `/api/auth/logout` then reloads, and skips `auth/me|login|register|logout` paths to avoid infinite-loop on initial auth probe (orchestrator-fixed bug).
- [x] `App.js`: replaced `token` state with `loggedIn` + `authChecked` flags. Initial `GET /api/auth/me` decides logged-in state. `handleAuth()` takes no arg. `handleLogout` calls `/api/auth/logout`.
- [x] `AuthScreen.js`: `onAuth()` invoked with no argument; the cookie is set by the server.
- [x] CSRF middleware (`backend/middleware/csrf.py`, 64 lines): double-submit cookie pattern. Skips safe methods, exempts `/api/auth/login` + `/api/auth/register`, skips Bearer-only requests (CLI/SDK). Uses `secrets.compare_digest` for timing-safe comparison. Sets a fresh `keyforge_csrf` cookie when missing or under 30 chars. Wired in `server.py` between RateLimit and Sanitization.
- [x] Acceptance: JWT cookie is `HttpOnly`, so `document.cookie` cannot read it from JS; XSS payloads cannot exfiltrate the token. Pytest 370 passed locally; backend boots cleanly with 6 middleware (was 5).

---

## Tier 2: Become an Issuer
**Goal:** "Click a button, get a credential" works end-to-end for at least one provider, with a generic pattern others can plug into.
**Status:** Not started.
**Estimate:** 1-2 weeks per provider. GitHub first.

### 2.1 Provider abstraction layer
- [ ] Define a `CredentialIssuer` interface in `backend/key_types/` or new `backend/issuers/`. Methods: `start_oauth(user, scope) -> auth_url`, `complete_oauth(user, code) -> credential`, `mint_scoped_credential(user, scope) -> credential`, `revoke(credential)`.
- [ ] Each provider implements the subset that makes sense. GitHub does all four; AWS does mint+revoke via STS; Stripe/OpenAI implement none and fall back to inline guided walkthrough (Tier 3).
- [ ] Database schema: extend credential records with `issuer`, `issued_at`, `revocable`, `scope`.
- [ ] Acceptance: a `tests/test_issuers_interface.py` verifies the interface contract with a fake issuer.

### 2.2 GitHub issuer (proof point)
- [ ] Register a GitHub App (not OAuth App; fine-grained permissions). Owner sets `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_APP_CLIENT_ID`, `GITHUB_APP_CLIENT_SECRET` in env. Document in README and `.env.example`.
- [ ] Backend route `POST /api/issuers/github/start` returns the install URL. `GET /api/issuers/github/callback` handles the redirect, stores installation token.
- [ ] Backend route `POST /api/issuers/github/mint` body: `{repo: "owner/name", permissions: [...]}`. Mints a fine-grained PAT or installation access token scoped to that repo. Stores it as a normal KeyForge credential, encrypted at rest, with `issuer="github"`.
- [ ] Frontend: a "Connect GitHub" button on the dashboard empty state. Once connected, "Generate key for repo X" inline action. Never shows the PAT to the user; copy-button only at use time.
- [ ] Acceptance: a non-technical user clicks Connect GitHub, picks a repo, clicks Generate, and now has a working credential they can use via the proxy without ever visiting GitHub settings.

### 2.3 AWS issuer
- [ ] One-time setup wizard: user creates an IAM role with a trust policy pointing at KeyForge's AWS account (or runs a CloudFormation template KeyForge generates). Documented in the wizard.
- [ ] `mint_scoped_credential` calls `sts:AssumeRole` with a session policy. Returns short-lived (1 hour default) credentials.
- [ ] Auto-rotation actually works for AWS (re-mint on expiry).
- [ ] Acceptance: minted creds work against `aws sts get-caller-identity`.

### 2.4 Inline guided walkthroughs (for providers without mint APIs)
- [ ] Build a JSON-driven walkthrough engine. Each provider has `walkthroughs/<provider>.json` with: steps, screenshots/links, validation regex for the pasted credential, suggested scopes.
- [ ] Frontend renders the walkthrough as a stepper inside the credential-add modal. Replaces the current bare "Enter API key" field for these providers.
- [ ] Acceptance: Stripe and OpenAI both have walkthroughs that a non-technical user can follow start to finish.

### 2.5 Make auto-rotation real (not "simulated")
- [ ] `backend/routes/auto_rotation.py:208-267` currently returns `status="simulated"`. Replace with calls into the new issuer interface: `issuer.mint_scoped_credential` for the same scope, then update the credential record.
- [ ] Schedule via the existing rotation tracker; surface failures in the audit log.
- [ ] Acceptance: a credential with a 7-day rotation policy actually gets rotated on day 7 with a new value, not a status string.

---

## Tier 3: Strip Jargon and Add Hand-Holding
**Goal:** First-time non-technical user gets to "I have a working credential" in under 3 minutes with zero unexplained terms.
**Status:** Not started.
**Estimate:** 3-5 days.

### 3.1 First-run wizard
- [ ] Replace the empty-zeros Dashboard for users with 0 credentials with a guided wizard: "Welcome -> Connect a provider -> Generate your first credential -> You're done".
- [ ] Wizard state in user record so it doesn't re-show.
- [ ] Acceptance: a fresh signup never sees the four-zero metric cards as their first view.

### 3.2 Hide advanced features behind a toggle
- [ ] Sidebar in `frontend/src/App.js:76-132` has 40+ items. Tag each as "Basic" or "Advanced". Default view shows only Basic. An Advanced toggle in profile reveals the rest.
- [ ] Basic = Credentials, Add, Audit Log (read-only summary), MFA, Profile.
- [ ] Advanced = KMS, Envelope Encryption, Field Encryption, Audit Integrity, IP Allowlist, Cost Estimation, etc.
- [ ] Acceptance: a brand new user sees < 8 sidebar items.

### 3.3 Tooltip every jargon term
- [ ] Inventory every UI string with jargon: TOTP, MFA, KMS, TTL, CIDR, envelope, DEK, KEK, PAT, OAuth, JWT, HMAC, RBAC.
- [ ] Build a `<JargonTerm term="TOTP">` component that wraps the term, shows the human translation on hover, and links to a glossary modal.
- [ ] Apply to every component flagged in the audit (MFASetup, EnvelopeEncryption, KMSManager, CredentialProxy, IPAllowlist, FieldEncryption, App sidebar).
- [ ] Acceptance: a Cmd+F across `frontend/src/components/` for any jargon term shows it wrapped in `<JargonTerm>` everywhere.

### 3.4 Replace "Add Credential" with provider-aware flow
- [ ] When user picks GitHub, route to GitHub issuer flow (Tier 2.2).
- [ ] When user picks Stripe/OpenAI/etc., route to walkthrough (Tier 2.4).
- [ ] When user picks "Other", show the current bare paste-key form.
- [ ] Acceptance: the word "API key" never appears as the first thing a non-technical user is asked for.

---

## Tier 4: Finish or Remove the Stubs
**Goal:** Every UI element either does what it claims or is gone.
**Status:** Not started.
**Estimate:** 2-3 days (mostly deletions and feature-flagging).

### 4.1 Decide and act on each stub
- [ ] `backend/routes/breach_detection.py` returns hardcoded zeros. Decide: implement against HaveIBeenPwned or remove the route + UI.
- [ ] `backend/routes/cost_estimation.py` returns "No pricing data available". Decide: ship a basic CSV-driven estimate or remove.
- [ ] `tools/vscode_extension/`: implement the four commands or remove the directory.
- [ ] `integrations/kubernetes/`: build, test, publish an image; or move to `experimental/` with a clear status.
- [ ] `integrations/terraform/`: compile and publish the provider; or move to `experimental/`.

### 4.2 CI hardening after Tier 1 is green
- [ ] Add a `coverage` floor (start at the actual current % to avoid regression, raise over time).
- [ ] Add e2e tests to CI (currently only run locally).
- [ ] Add a smoke job that does `docker compose up`, hits `/api/health`, tears down. This catches Dockerfile regressions.

### 4.3 Security follow-ups
- [ ] Add CSRF protection (covered partially in 1.7; finish here if not done).
- [ ] Make rate limiter per-user when authenticated, fall back to per-IP when not.
- [ ] Fix `backend/security.py:40-42` to log a generic "decryption failed" without the exception text.
- [ ] Add password complexity requirement on password-change endpoint (not just on signup).
- [ ] Run `bandit` and `safety` and triage the findings (workflow already exists, results currently suppressed with `|| true`).

---

## Pickup checklist for next session

1. Read this file end to end.
2. Read `tasks/lessons.md`.
3. Read the four memory files in `C:\Users\dlaur\.claude\projects\D--Projects-Open-Source-KeyForge\memory\` (auto-loaded via MEMORY.md index).
4. Read `CLAUDE.md` at repo root for project-specific conventions.
5. Verify the audit findings still hold (`python -m pytest tests/ --collect-only -q`, `git status`, `git log --oneline -10`).
6. Pick the next unchecked Tier 1 item. Spawn subagents in parallel for independent items.
