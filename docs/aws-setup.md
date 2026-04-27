# KeyForge AWS Setup, step by step

This is the standalone walkthrough for wiring AWS into KeyForge so the AWS
issuer can mint short-lived `sts:AssumeRole` credentials on demand. The
operator-side runbook in `docs/operator-setup.md` covers GitHub + AWS
together; this file is AWS-only and self-contained, suitable for following
on a different device than the one running KeyForge.

You will work in two roles:

1. **Operator** (you): the person running the KeyForge deployment. Configures
   KeyForge once so it can call `sts:AssumeRole`. Steps 1 to 6.
2. **End user** (also you on first run, then real users later): registers a
   role in their own AWS account that KeyForge is allowed to assume, then
   mints credentials. Steps 7 to 12.

Every step has a verification command. Do not skip them.

---

## Prerequisites

- A working KeyForge instance you can hit with `curl` from the command line
  (local: `http://localhost:8001`; production: whatever you deployed).
- A registered KeyForge user account (`POST /api/auth/register` or via the
  web UI). You will log in to that user later.
- Access to an AWS account where KeyForge runs (the "operator" account). You
  need IAM permissions to create users / attach policies, OR an EC2 instance
  role you can edit.
- Access to an AWS account where the credentials should be minted (the
  "user" account). It can be the same account as the operator account; in
  production it would be the user's own account.
- The `aws` CLI installed and authenticated against your operator account
  for the verification commands. (`aws --version`, `aws sts
  get-caller-identity`.)
- `curl` and `jq` for the verification commands.

---

## Operator side (you, configuring KeyForge once)

### Step 1: Find KeyForge's AWS account ID

This is the account ID of the AWS account where KeyForge itself runs. The
trust policy you hand out to users will name this account as the principal
allowed to call `sts:AssumeRole` on their roles.

Run from a shell authenticated against the KeyForge operator account:

```bash
aws sts get-caller-identity --query Account --output text
```

You get back a 12-digit number, e.g. `123456789012`. Write this down. It is
the value of `KEYFORGE_AWS_ACCOUNT_ID` you will set in step 4.

### Step 2: Decide how KeyForge authenticates to its OWN AWS account

KeyForge calls `sts:AssumeRole` from its own AWS principal. Pick the option
that fits your deployment:

| Deployment shape | Auth path | Steps |
|------------------|-----------|-------|
| EC2 / Fargate / ECS / EKS in production | Instance / task role | Skip step 3. Boto3 picks it up from the instance metadata service. |
| Container or VM where you cannot attach a role | IAM user with access keys | Do step 3, then put `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` into KeyForge's env in step 4. |
| Local laptop running `docker compose up` | `~/.aws/credentials` | Skip step 3. Boto3 picks them up. Set `AWS_REGION` in step 4. |

### Step 3 (only if using an IAM user): Create the `keyforge-service` IAM user

In the AWS console for your operator account:

1. Go to **IAM > Users > Add user**.
2. User name: `keyforge-service`.
3. Access type: **Programmatic access** only. Do NOT give console access.
4. Click **Next: Permissions** and pick **Attach policies directly**.
5. Click **Create policy** in a new tab. Pick the **JSON** tab and paste:

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

   The wildcard on the account id is intentional. Each user creates their
   own role with the fixed name `KeyForgeAssumableRole` in their own
   account, and KeyForge needs to assume into all of them. The fixed
   role-name suffix keeps the policy narrow even with the account wildcard.

6. Name the policy `KeyForgeAssumeRolePolicy`. Save.
7. Back on the user-creation tab, refresh the policy list, attach
   `KeyForgeAssumeRolePolicy`. Finish creating the user.
8. On the final screen, AWS shows the **Access key ID** and **Secret
   access key** ONCE. Copy both values to a safe place. AWS will never
   show the secret again.

### Step 4: Wire env vars into KeyForge's `backend/.env`

Append to `backend/.env` on the host running KeyForge:

```ini
# AWS region for the STS client. Falls back to AWS_DEFAULT_REGION, then
# us-east-1.
AWS_REGION=us-east-1

# KeyForge's own AWS account id, from step 1.
KEYFORGE_AWS_ACCOUNT_ID=123456789012
```

If you are using the IAM user path from step 3 (not an instance role and not
a local `~/.aws/credentials`), also append:

```ini
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=<the secret from step 3>
```

Do not commit `backend/.env`. It is gitignored. In production, prefer
your platform's secret-storage feature (AWS Secrets Manager, GCP Secret
Manager, your orchestrator's env-injection mechanism) over a literal `.env`
file.

### Step 5: Restart the backend

If you run KeyForge with Docker Compose:

```bash
docker compose down
docker compose up --build
```

If you run uvicorn directly, kill the process and start it again. The new
env vars are picked up at startup, not at runtime.

### Step 6: Verify the operator side

You need a logged-in session for this. Either log in via the web UI and
copy the `keyforge_token` cookie, or use the CLI:

```bash
# From the repo root, on the host running KeyForge.
python tools/cli.py login --username YOUR_USERNAME --password YOUR_PASSWORD
```

Then hit the AWS issuer status endpoint:

```bash
curl -s http://localhost:8001/api/issuers/aws/status \
  -H "Authorization: Bearer $(python -c \
    'import json,pathlib; print(json.loads(pathlib.Path.home().joinpath(\".keyforge/config.json\").read_text())[\"token\"])')" \
  | jq
```

You want exactly this shape (with your own account id and region):

```json
{
  "boto3_installed": true,
  "keyforge_aws_account_id_set": true,
  "user_role_arn_configured": false,
  "aws_region": "us-east-1"
}
```

If `boto3_installed` is `false`: the backend image is missing the optional
dep. Rebuild with `docker compose up --build --force-recreate` or `pip
install boto3` inside the running container.

If `keyforge_aws_account_id_set` is `false`: the env var did not get loaded.
Check `docker compose config | grep KEYFORGE_AWS_ACCOUNT_ID`. If the line is
missing or empty, the value did not propagate from `backend/.env`.

If `aws_region` is not what you set: the `env_file` directive on the backend
service in `docker-compose.yml` may be missing or `required: false` might
have skipped loading the file. Check that `backend/.env` exists and is
readable.

`user_role_arn_configured: false` is correct at this stage; you have not
configured the user-side role yet.

**Operator side done.** Mark task #9 complete in `tasks/todo.md`. Move on
to the user side.

---

## User side (you walking through the first user, then real users later)

### Step 7: Get the CloudFormation trust-policy template

Logged in as a regular KeyForge user (the same one from step 6 is fine for
the first run), hit:

```bash
curl -s http://localhost:8001/api/issuers/aws/trust-policy-template \
  -H "Authorization: Bearer ${KEYFORGE_TOKEN}" \
  | jq -r .template > keyforge-aws-trust.yaml
```

(Replace `KEYFORGE_TOKEN` with the JWT from your config or session.)

`keyforge-aws-trust.yaml` should now contain a CloudFormation YAML body. The
two placeholders are already substituted: `<KEYFORGE_AWS_ACCOUNT_ID>` from
your operator setup, and `<YOUR_USER_ID>` from the authenticated user's
KeyForge id. The template is roughly this shape:

```yaml
# AWS CloudFormation template - KeyForge IAM role trust policy.
AWSTemplateFormatVersion: '2010-09-09'
Description: KeyForge IAM role allowing the KeyForge service account to
  assume this role and mint short-lived credentials on behalf of users.
Resources:
  KeyForgeAssumableRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: KeyForgeAssumableRole
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              AWS: arn:aws:iam::123456789012:root      # KeyForge's account
            Action: sts:AssumeRole
            Condition:
              StringEquals:
                sts:ExternalId: KEYFORGE_USER_ID_HERE  # your user id
      MaxSessionDuration: 3600
      Policies:
        - PolicyName: ReadOnlyByDefault
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - 'iam:GetUser'
                  - 'sts:GetCallerIdentity'
                Resource: '*'
Outputs:
  RoleArn:
    Description: ARN to paste back into KeyForge
    Value: !GetAtt KeyForgeAssumableRole.Arn
```

The `ReadOnlyByDefault` inline policy is a deliberately tiny default. Once
the role exists, you can attach broader policies in your own account
according to what you actually want minted credentials to be allowed to do.
The role's permissions can be narrowed further per-mint via the
`session_policy` body field on `POST /api/issuers/aws/mint`.

### Step 8: Apply the template in YOUR aws account

This step happens in the **end-user's** AWS account, which can be different
from the operator account. For the first run, it can be the same account.

In the AWS console for the user account:

1. Go to **CloudFormation > Stacks > Create stack > With new resources**.
2. Pick **Upload a template file** and upload `keyforge-aws-trust.yaml`.
3. Click **Next**.
4. Stack name: `KeyForgeAssumableRole`.
5. Leave parameters empty (the template has none after rendering).
6. Click **Next**, **Next** again.
7. Check **I acknowledge that AWS CloudFormation might create IAM
   resources**.
8. Click **Submit**.
9. Wait for the stack status to reach `CREATE_COMPLETE`. Refreshing every
   ten seconds is fine; the role takes about 15 to 30 seconds to create.

### Step 9: Copy the role ARN

In the same CloudFormation stack:

1. Click the **Outputs** tab.
2. Copy the `RoleArn` value. It looks like
   `arn:aws:iam::USER_ACCOUNT_ID:role/KeyForgeAssumableRole`.

### Step 10: Tell KeyForge about the role

```bash
curl -s -X POST http://localhost:8001/api/issuers/aws/configure \
  -H "Authorization: Bearer ${KEYFORGE_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"role_arn": "arn:aws:iam::USER_ACCOUNT_ID:role/KeyForgeAssumableRole"}' \
  | jq
```

KeyForge validates the ARN format and stores it on your user document.
Response:

```json
{
  "role_arn": "arn:aws:iam::USER_ACCOUNT_ID:role/KeyForgeAssumableRole",
  "trust_policy_template_url": "/api/issuers/aws/trust-policy-template"
}
```

If you get a `400` with `Invalid role ARN`, the value did not match the IAM
ARN regex. Re-copy from the CloudFormation outputs tab; do not type it by
hand.

### Step 11: Mint a credential

```bash
curl -s -X POST http://localhost:8001/api/issuers/aws/mint \
  -H "Authorization: Bearer ${KEYFORGE_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"duration_seconds": 3600}' \
  | jq
```

KeyForge calls `sts:AssumeRole` against your role, captures the resulting
`AccessKeyId` + `SecretAccessKey` + `SessionToken` + `Expiration`, encrypts
them with the per-user envelope encryption key, and stores them as a
KeyForge credential. The mint response returns metadata only; it never
returns the plaintext STS triple to a browser session.

```json
{
  "id": "abc-123-...",
  "api_name": "aws_sts_KeyForgeAssumableRole",
  "issuer": "aws",
  "scope": "role:arn:aws:iam::USER_ACCOUNT_ID:role/KeyForgeAssumableRole",
  "revocable": false,
  "issued_at": "2026-04-27T05:00:00Z",
  "expires_at": "2026-04-27T06:00:00Z"
}
```

If you get a `401 AccessDenied`: the trust policy in the role does not name
KeyForge's account as a trusted principal, OR the External ID condition does
not match your KeyForge user id. Re-apply the unmodified template.

If you get a `502 Bad Gateway`: KeyForge could not reach STS. Check the
backend's network egress.

### Step 12: Verify the credential actually works

The plaintext is never returned to browser sessions. To exercise it
end-to-end, pull the credential through the CLI or the proxy. With the CLI
(simplest):

```bash
python tools/cli.py list
# Find the row whose api_name starts with aws_sts_KeyForgeAssumableRole.
# Its id is what you reference below.

# Pull the plaintext value (CLI uses Bearer auth, which the
# include-plaintext gate respects):
python tools/cli.py get <CREDENTIAL_ID>
```

The output is the JSON triple `{AccessKeyId, SecretAccessKey, SessionToken,
Expiration}`. Export those into a fresh shell:

```bash
export AWS_ACCESS_KEY_ID=ASIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...

aws sts get-caller-identity
```

You should see something like:

```json
{
  "UserId": "AROA...:keyforge-USER_ACCOUNT_ID-...",
  "Account": "USER_ACCOUNT_ID",
  "Arn": "arn:aws:sts::USER_ACCOUNT_ID:assumed-role/KeyForgeAssumableRole/keyforge-..."
}
```

Confirming the assume-role actually happened:

- `Account` is the USER account, not the KeyForge operator account.
- `Arn` starts with `arn:aws:sts::.../assumed-role/KeyForgeAssumableRole/`.

If `Arn` shows the IAM user that KeyForge runs as instead of the assumed
role, the assume-role never happened. KeyForge would have logged a
`BotoCoreError` or `ClientError`. Check the backend log:

```bash
docker compose logs backend --tail 100 | grep -i "assume_role"
```

If you see `Account` matching the user account and `Arn` matching the
assumed role, you are done. Mark task #9 complete in `tasks/todo.md`.

---

## Troubleshooting checklist

If a step fails and the symptom is not in the per-step lists above, work
through these in order:

1. `aws sts get-caller-identity` from the operator host returns the
   operator account, not an error. If it errors, the operator host has no
   AWS credentials configured at all and step 2 was skipped.
2. `KEYFORGE_AWS_ACCOUNT_ID` in `backend/.env` matches what step 1 returned
   exactly. Off-by-one digit kills the whole flow.
3. The CloudFormation stack in the user account exists and is in
   `CREATE_COMPLETE`, not `ROLLBACK_COMPLETE` or `CREATE_FAILED`. If
   rolled back, click the Events tab and read the failure reason. The most
   common cause is the user account already has a role named
   `KeyForgeAssumableRole`; either delete that role first or rename the new
   one in the template.
4. The role's trust policy in the user account, viewed in the AWS console
   under **IAM > Roles > KeyForgeAssumableRole > Trust relationships**,
   shows the operator account id (not `<KEYFORGE_AWS_ACCOUNT_ID>`) and the
   correct user External ID. If the placeholders are still literal text,
   `KEYFORGE_AWS_ACCOUNT_ID` was unset when you fetched the template;
   redo step 4, then redo step 7 to fetch a freshly-rendered template.
5. The `sts:AssumeRole` call from KeyForge to the user account is allowed
   by SCP / OU policy if you are inside an AWS Organization. If your
   security tooling blocks cross-account `sts:AssumeRole`, the call will
   fail with `AccessDenied` even though the trust policy is correct.

If none of those help, capture the failing curl output plus the backend's
last 200 log lines and file an issue at
https://github.com/DarkHorse-InfoSec/KeyForge/issues. Do not include the
plaintext STS credentials or any access keys in the issue body; redact
them first.
