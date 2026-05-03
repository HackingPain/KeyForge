# KeyForge Operator Setup

This runbook walks an operator through the two external integrations KeyForge
needs before its credential-issuer features (Tier 2 of `tasks/todo.md`) work
end to end against real providers:

1. **GitHub App registration** unblocks the Connect-GitHub-and-mint-fine-grained-PAT flow (Tier 2.2).
2. **AWS credentials configuration** unblocks STS assumed-role minting (Tier 2.3).

Each step has a verification command. Do not skip those; they catch every
common misconfiguration in the same place each time.

The walkthrough assumes you have:

- A local clone of KeyForge with `python tools/cli.py init` already run.
- Either the backend running locally (`docker compose up --build`) or a
  deployed instance you control.
- Owner access to the `DarkHorse-InfoSec` GitHub org (or whichever org will
  own the App).
- An AWS account where KeyForge will run, plus the ability to create IAM
  users / roles in that account.

If something fails, jump to the Troubleshooting section at the bottom.

---

## Part 1: Register the GitHub App

This is the last step before "Connect GitHub" goes from a button rendered
against mocked HTTP to a button that actually mints fine-grained PATs.

### 1.1 Decide where the App lives

Open https://github.com and **switch to the `DarkHorse-InfoSec` org context**
(account dropdown at the top right, click "DarkHorse-InfoSec"). Apps owned by
the org can be installed by anyone in the org and against any org-owned repo;
apps owned by your personal account can only be installed against repos in
that account. Pick the org.

### 1.2 Open the new-app form

Navigate to:

```
https://github.com/organizations/DarkHorse-InfoSec/settings/apps/new
```

If GitHub shows you a "You don't have access to this page" message, you are
not an org owner. Ask whoever is to add you as an owner first.

### 1.3 Fill in the form

| Field                         | Value                                                                                          |
| ----------------------------- | ---------------------------------------------------------------------------------------------- |
| GitHub App name               | `KeyForge` (production) or `KeyForge Dev` (development; the names must be globally unique)     |
| Description                   | one-liner describing what the app does, e.g. "Mints fine-grained credentials for KeyForge users." |
| Homepage URL                  | `https://keyforge.darkhorseinfosec.com` (or `http://localhost:3000` for dev)                   |
| Identifying and authorizing users -> Callback URL | leave blank (we do not use the user OAuth flow)                            |
| Identifying and authorizing users -> Request user authorization (OAuth) during installation | leave **unchecked**                  |
| Post installation -> Setup URL | the **backend** callback path, not the frontend: `http://localhost:8001/api/issuers/github/callback` for dev, `https://api.keyforge.darkhorseinfosec.com/api/issuers/github/callback` for prod |
| Post installation -> Redirect on update | **check this box**                                                                  |
| Webhook -> Active             | **uncheck this**. KeyForge does not consume webhook events yet.                                |
| Webhook URL / Webhook secret  | leave blank.                                                                                   |
| Permissions -> Repository -> Contents | **Read and write** (so users can pick read-only or read-write at mint time)            |
| Permissions -> Repository -> Metadata | **Read-only** (this is mandatory; GitHub auto-includes it)                             |
| Permissions -> Repository -> Pull requests | **Read and write**                                                                |
| (Other permissions)           | leave at "No access" unless you have a specific user request                                   |
| Where can this GitHub App be installed? | **Any account** if you want public users; **Only on this account** for org-only          |

### 1.4 Click "Create GitHub App"

The green button at the very bottom of the form.

> **This is the step you got stuck on the first time.** App ID, Client ID,
> the client-secret button, and the private-key button only appear *after*
> this click. The form page does not show them.

GitHub redirects you to the **app settings page**:

```
https://github.com/organizations/DarkHorse-InfoSec/settings/apps/<your-slug>
```

`<your-slug>` is GitHub's URL-safe lowercase version of the App name you
chose (so `KeyForge` -> `keyforge`, `KeyForge Dev` -> `keyforge-dev`). Bookmark
this URL; you will come back to it.

### 1.5 Collect five values

On the app settings page:

1. **App ID** (top of the page, "About" card). It is a number, e.g. `1234567`.
   This is `GITHUB_APP_ID`.
2. **Client ID** (same card, just below App ID, e.g. `Iv1.abcdef0123456789`).
   This is `GITHUB_APP_CLIENT_ID`.
3. **Client secret** scroll down to the "Client secrets" section -> click
   **Generate a new client secret** -> copy the value the page shows you
   immediately. GitHub never shows it again. This is `GITHUB_APP_CLIENT_SECRET`.
4. **Slug** the URL-safe name from the URL bar, e.g. `keyforge`. This is
   `GITHUB_APP_SLUG`.
5. **Private key** scroll further to "Private keys" -> click **Generate a
   private key**. A `.pem` file downloads. Save it somewhere outside the repo,
   e.g. `~/.keyforge/github-app.pem`. This is the value of
   `GITHUB_APP_PRIVATE_KEY` (you can pass either the path or the PEM contents
   directly).

### 1.6 Wire the env vars

Append the following block to `backend/.env` (for local dev) or to the env
file your deployment uses:

```ini
GITHUB_APP_ID=1234567
GITHUB_APP_PRIVATE_KEY=/home/you/.keyforge/github-app.pem
GITHUB_APP_CLIENT_ID=Iv1.abcdef0123456789
GITHUB_APP_CLIENT_SECRET=<the secret from step 1.5>
GITHUB_APP_SLUG=keyforge
GITHUB_APP_INSTALL_REDIRECT_URL=http://localhost:8001/api/issuers/github/callback
KEYFORGE_FRONTEND_URL=http://localhost:3000
```

If you have set `KEYFORGE_FRONTEND_PORT` (e.g. because port 3000 is taken locally), `KEYFORGE_FRONTEND_URL` and the GitHub App's Homepage URL must match the new port — the install-redirect handshake compares the two literally.

`GITHUB_APP_PRIVATE_KEY` accepts either a filesystem path (the safer form;
the file stays out of `.env`) **or** the PEM contents directly (paste the
whole `-----BEGIN ... -----END` block). The KeyForge backend detects which
form you passed.

`GITHUB_APP_INSTALL_REDIRECT_URL` MUST match the Setup URL you set in
step 1.3. If they drift, the OAuth-style state JWT KeyForge signs into the
install URL will not validate on return.

### 1.7 Restart the backend

```bash
docker compose down
docker compose up --build
```

If you are running uvicorn bare-metal, just kill and restart it.

### 1.8 Verify

Log in to KeyForge in the browser. Go to **Add Credential** -> pick
**GitHub** from the provider dropdown. The bare paste form should be replaced
by a "Connect GitHub" button.

Click **Connect GitHub**. A new tab opens to:

```
https://github.com/apps/<your-slug>/installations/new?state=<signed JWT>
```

Pick the repos you want KeyForge to be able to mint credentials for, click
Install. GitHub bounces you back to KeyForge with `?github=connected` in the
URL. The dashboard refreshes the installations list.

Now click **Generate** for one of the repos -> KeyForge calls
`POST /app/installations/{id}/access_tokens` with that repo as the scope ->
the resulting fine-grained installation token gets encrypted at rest and
shows up in your Credentials list. The token is never rendered to the DOM;
copy it via the proxy or the CLI when you need to use it.

### 1.9 Common failures

- **The new tab shows GitHub's "404 not found" page.** Your `GITHUB_APP_SLUG`
  is wrong. Check the URL bar of the app settings page in step 1.4.
- **GitHub redirects back with `?github=error&reason=invalid_state`.** Your
  `GITHUB_APP_INSTALL_REDIRECT_URL` does not match the Setup URL on the App.
  Edit the App -> Post installation -> Setup URL -> save -> retry.
- **GitHub redirects back with `?github=error&reason=upstream`.** The App
  could not produce an installation token. Common causes: the private key
  path is wrong (check `ls -la $GITHUB_APP_PRIVATE_KEY`), or the PEM contents
  in the env got truncated (newlines stripped). Re-download the `.pem` from
  step 1.5.
- **No "Connect GitHub" button appears in the UI.** The frontend is talking
  to the backend OK but the backend has no GitHub issuer registered. Check
  the backend logs at startup: you should see no `IssuerNotSupported` lines
  related to GitHub. If you see one, an env var above is missing or empty.

When you can mint a token end-to-end and it shows up in the Credentials list,
mark task #8 complete in `tasks/todo.md` and move on to Part 2.

---

## Part 2: Configure AWS

This is the last step before AWS Issuer's `mint_scoped_credential` goes from
mocking `boto3.client('sts').assume_role` to actually calling STS.

### 2.1 Decide how KeyForge authenticates to its OWN AWS account

KeyForge calls `sts:AssumeRole` against the user's role from KeyForge's
*own* AWS principal. Pick the principal flavour that fits your deployment:

- **Production on EC2 / Fargate / ECS / EKS:** attach an IAM role to the
  instance / task / pod. The role needs `sts:AssumeRole` permission against
  whatever role ARNs your users are going to register. boto3 picks this up
  from the instance metadata service automatically; you set zero env vars in
  KeyForge.
- **Containers / CI / dev box (no instance role available):** create a
  dedicated IAM user. Step 2.2 walks through it.
- **Local dev on your laptop:** if you already run `aws configure` and have
  `~/.aws/credentials` set up, boto3 will find it. Skip to step 2.4.

### 2.2 (If using an IAM user) Create the KeyForge service user

In the AWS console, IAM -> Users -> Add user:

| Field          | Value                            |
| -------------- | -------------------------------- |
| User name      | `keyforge-service`               |
| Access type    | check **Programmatic access** only |

On the next screen, attach a custom inline policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeRoleIntoUserAccounts",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::*:role/KeyForgeAssumableRole"
    }
  ]
}
```

The wildcard on the account id is intentional: each user creates the
trust-policy role in their own account, and KeyForge needs to assume into all
of them. The role-name suffix is fixed (`KeyForgeAssumableRole`) so the policy
stays narrow.

Finish creation. Copy the **Access key ID** and **Secret access key** that
appear on the final screen. AWS only shows the secret once.

### 2.3 (If using an IAM user) Wire its credentials

Append to `backend/.env`:

```ini
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=<from step 2.2>
AWS_REGION=us-east-1
```

If you are deploying to a real environment, prefer the deployment platform's
secret-storage feature over a literal `.env` file (e.g., AWS Secrets Manager,
GCP Secret Manager, your orchestrator's env-injection mechanism).

### 2.4 Find KeyForge's account ID and set `KEYFORGE_AWS_ACCOUNT_ID`

KeyForge needs to know its own AWS account number so the trust-policy
template it hands out to users renders with the right `Principal` ARN. Run:

```bash
aws sts get-caller-identity --query Account --output text
```

That prints a 12-digit number. Append to `backend/.env`:

```ini
KEYFORGE_AWS_ACCOUNT_ID=123456789012
```

Without this var, the `GET /api/issuers/aws/trust-policy-template` endpoint
renders the template with a literal `<KEYFORGE_AWS_ACCOUNT_ID>` placeholder.
Users would have to ask you for the number out-of-band, which defeats the
"copy this template, run it" UX.

### 2.5 Restart the backend

```bash
docker compose down
docker compose up --build
```

### 2.6 Verify the operator side

```bash
curl -s http://localhost:8001/api/issuers/aws/status -b cookies.txt
```

(replace `cookies.txt` with whatever cookie jar your test login produced).

The response should be:

```json
{
  "boto3_installed": true,
  "keyforge_aws_account_id_set": true,
  "user_role_arn_configured": false,
  "aws_region": "us-east-1"
}
```

If `boto3_installed` is `false`, your image is missing the optional dep:
rebuild with `docker compose up --build --force-recreate` or `pip install
boto3` in the backend container.

If `keyforge_aws_account_id_set` is `false`, your env var did not get loaded.
Check `docker compose config | grep KEYFORGE_AWS_ACCOUNT_ID`.

### 2.7 Walk through the user side once yourself

This is the flow your users will follow. Do it as your own user account
once so you know what UX they will see.

1. **Get the trust-policy template.**
   `GET /api/issuers/aws/trust-policy-template` (authenticated). The response
   is JSON with a `template` field containing a CloudFormation YAML body. The
   `<KEYFORGE_AWS_ACCOUNT_ID>` placeholder is already filled in (because of
   step 2.4) and `<YOUR_USER_ID>` is filled in with your KeyForge user id.
2. **Apply the template in your own AWS account.** Save the YAML to a file.
   In the AWS console, CloudFormation -> Create stack -> Upload template ->
   pick the file. Apply. Wait for the stack to reach `CREATE_COMPLETE`.
3. **Copy the role ARN.** In the stack's Outputs tab, copy the `RoleArn`
   value. It looks like `arn:aws:iam::USER_ACCOUNT_ID:role/KeyForgeAssumableRole`.
4. **Tell KeyForge about the role.**
   `POST /api/issuers/aws/configure` body
   `{"role_arn": "arn:aws:iam::USER_ACCOUNT_ID:role/KeyForgeAssumableRole"}`.
   KeyForge validates the ARN format and stores it on your user document.
5. **Mint a credential.**
   `POST /api/issuers/aws/mint` body `{"duration_seconds": 3600}`.
   KeyForge calls `sts:AssumeRole` against your role and stores the resulting
   `{AccessKeyId, SecretAccessKey, SessionToken, Expiration}` blob, encrypted
   at rest. The mint response includes the credential id and metadata; the
   plaintext STS triple is never returned to a browser session.
6. **Spot-check that the credential actually works.** Pull the plaintext
   triple via the CLI / SDK / proxy. Set the three values as
   `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` and
   run:

   ```bash
   aws sts get-caller-identity
   ```

   The response should show your user role's identity (the assumed-role ARN),
   not KeyForge's IAM user. If you see KeyForge's identity, the assume-role
   never happened; check logs.

### 2.8 Common failures

- **`POST /api/issuers/aws/mint` returns 401 Unauthorized: AccessDenied.**
  The trust policy in the user's role does not name KeyForge's account as a
  trusted principal. Either KEYFORGE_AWS_ACCOUNT_ID was wrong when the
  template was generated, or the user edited the template before applying.
  Have them re-apply the unmodified template.
- **`POST /api/issuers/aws/mint` returns 401 with `Conditional check failed:
  sts:ExternalId`.** The trust policy expects an External ID condition that
  KeyForge does not currently send. Drop the `Condition: StringEquals:
  sts:ExternalId` block from the template until External ID support is wired
  (tracked as a future hardening pass).
- **`POST /api/issuers/aws/mint` returns 502 Bad Gateway with `BotoCoreError`.**
  Network or DNS to STS is broken. Check that the backend container can
  reach the public internet; STS is a public endpoint.
- **`GET /api/issuers/aws/status` says `keyforge_aws_account_id_set: true` but
  the trust-policy template still has the placeholder.** You set the env var
  AFTER the backend started. Restart.

When you can `aws sts get-caller-identity` against a KeyForge-minted
credential and see the user's role identity, mark task #9 complete and move
on.

---

## Troubleshooting checklist (both parts)

If something failed and the symptom is not in the per-part lists above, work
through these in order:

1. `docker compose logs backend --tail 200` should not contain
   `IssuerNotSupported`, `Fernet key must be 32 url-safe base64-encoded
   bytes`, `JWTError`, or `ValueError` lines at startup. If it does, the
   message names the env var or path that is wrong; fix and restart.
2. `curl -s http://localhost:8001/api/health` returns
   `{"status": "healthy"}`. If not, the backend never finished booting.
3. `curl -s http://localhost:8001/api/issuers/github/installations -b
   cookies.txt` and `.../aws/status` both require auth. A 401 is expected
   without a cookie; a 200 with an empty list is what a freshly-set-up but
   unconnected user looks like.
4. The CSRF middleware blocks anonymous mutating requests with 403, not 401,
   from browser sessions. If you see 403 on a `POST` while testing with curl
   without a session, that is correct behaviour; pass `-H "X-CSRF-Token:
   $(grep keyforge_csrf cookies.txt | awk '{print $7}')"` to satisfy it.
5. The frontend talks to the backend through `REACT_APP_BACKEND_URL`. If the
   browser console shows fetch errors against an unexpected URL, check
   `frontend/.env` matches the deployed backend.

If none of those help, capture the failing curl + the backend logs around it
and file an issue at https://github.com/DarkHorse-InfoSec/KeyForge/issues
(or open a security advisory if it touches credential handling).
