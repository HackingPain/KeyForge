# KeyForge Terraform Provider

A Terraform provider for [KeyForge](../../README.md) that lets infrastructure-as-code teams manage and retrieve API credentials during `terraform plan` and `terraform apply`.

## Features

- **Resource `keyforge_credential`** - full CRUD lifecycle for credentials stored in KeyForge.
- **Data source `keyforge_credential`** - read-only lookup by credential ID or `api_name`. Returns the API key as a sensitive value.
- **Data source `keyforge_credentials`** - list all credentials with an optional `environment` filter.
- Automatic JWT-based authentication against the KeyForge API.
- All secret values are marked `Sensitive` so Terraform redacts them from console output and state diffs.

## Requirements

| Dependency | Version |
|---|---|
| Terraform | >= 1.0 |
| Go (to build) | >= 1.21 |
| KeyForge API | >= 4.1.0 |

## Installation

### Building from source

```bash
cd integrations/terraform
go build -o terraform-provider-keyforge
```

### Installing the binary

Place the compiled binary in your Terraform plugins directory:

```bash
# Linux / macOS
mkdir -p ~/.terraform.d/plugins/keyforge/keyforge/1.0.0/linux_amd64/
cp terraform-provider-keyforge ~/.terraform.d/plugins/keyforge/keyforge/1.0.0/linux_amd64/
```

Then reference the provider in your Terraform config:

```hcl
terraform {
  required_providers {
    keyforge = {
      source  = "keyforge/keyforge"
      version = "~> 1.0"
    }
  }
}
```

## Configuration

```hcl
provider "keyforge" {
  host  = "http://localhost:8000"   # or set KEYFORGE_HOST env var
  token = var.keyforge_token        # or set KEYFORGE_TOKEN env var
}
```

| Argument | Type | Required | Default | Description |
|---|---|---|---|---|
| `host` | `string` | Yes | `http://localhost:8000` | URL of the KeyForge API server. |
| `token` | `string` | Yes | - | JWT authentication token obtained via `POST /api/auth/login`. |

### Obtaining a token

```bash
curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"your-password"}' \
  | jq -r '.access_token'
```

Set it as an environment variable for hands-free usage:

```bash
export KEYFORGE_TOKEN="eyJhbGciOi..."
export KEYFORGE_HOST="http://localhost:8000"
```

## Resources

### `keyforge_credential`

Manages the full lifecycle (create, read, update, delete) of a credential in KeyForge.

#### Arguments

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `api_name` | `string` | Yes | - | API provider name (e.g. `openai`, `stripe`, `aws`). Forces replacement on change. |
| `api_key` | `string` | Yes | - | The secret API key. **Sensitive.** |
| `environment` | `string` | No | `development` | Target environment: `development`, `staging`, or `production`. |
| `credential_type` | `string` | No | `api_key` | Informational label (e.g. `api_key`, `oauth_token`, `ssh_key`). |

#### Attributes (computed)

| Name | Description |
|---|---|
| `id` | UUID of the credential in KeyForge. |
| `status` | Validation status: `active`, `inactive`, `expired`, or `invalid`. |
| `api_key_preview` | Masked preview showing only the last 4 characters. |
| `created_at` | ISO-8601 creation timestamp. |
| `last_tested` | ISO-8601 timestamp of the last validation test. |

#### Example

```hcl
resource "keyforge_credential" "stripe_prod" {
  api_name        = "stripe"
  api_key         = var.stripe_secret_key
  environment     = "production"
  credential_type = "api_key"
}
```

#### Import

Existing credentials can be imported by their UUID:

```bash
terraform import keyforge_credential.stripe_prod a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

## Data Sources

### `keyforge_credential`

Read-only lookup of a single credential by ID or `api_name`. Returns the API key as a sensitive value.

#### Arguments

| Name | Type | Required | Description |
|---|---|---|---|
| `credential_id` | `string` | One of | UUID of the credential. |
| `api_name` | `string` | One of | API provider name to search for. Returns the first match. |

> Exactly one of `credential_id` or `api_name` must be specified.

#### Attributes

| Name | Description |
|---|---|
| `api_key` | The API key value. **Sensitive.** |
| `environment` | Environment the credential belongs to. |
| `credential_type` | Type of credential. |
| `status` | Validation status. |
| `api_key_preview` | Masked preview. |
| `created_at` | Creation timestamp. |
| `last_tested` | Last validation timestamp. |

#### Example

```hcl
# Look up by name
data "keyforge_credential" "openai" {
  api_name = "openai"
}

# Look up by ID
data "keyforge_credential" "specific" {
  credential_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}

# Use the secret value
resource "aws_lambda_function" "worker" {
  # ...
  environment {
    variables = {
      OPENAI_API_KEY = data.keyforge_credential.openai.api_key
    }
  }
}
```

### `keyforge_credentials`

Lists credentials with an optional environment filter. Useful for discovering all secrets in a given environment.

#### Arguments

| Name | Type | Required | Description |
|---|---|---|---|
| `environment` | `string` | No | Filter by environment (`development`, `staging`, `production`). Omit to list all. |

#### Attributes

| Name | Description |
|---|---|
| `credentials` | List of credential objects, each containing: `id`, `api_name`, `api_key` (sensitive), `api_key_preview`, `environment`, `status`, `created_at`, `last_tested`. |

#### Example

```hcl
data "keyforge_credentials" "prod" {
  environment = "production"
}

output "prod_credential_count" {
  value = length(data.keyforge_credentials.prod.credentials)
}
```

## Full Example

See [`examples/main.tf`](examples/main.tf) for a complete working example that demonstrates:

- Provider configuration with variables
- Single credential lookup by `api_name` and by `credential_id`
- Listing production credentials
- Creating new credentials
- Injecting KeyForge secrets into AWS Lambda environment variables

## Security Considerations

- **Sensitive values**: All API keys are marked `Sensitive` in the Terraform schema. Terraform will not display them in plan output or CLI logs. However, they **are** stored in the Terraform state file.
- **State encryption**: Use a remote backend with encryption (e.g., S3 + KMS, Terraform Cloud) to protect secrets at rest.
- **Token rotation**: The JWT token used to authenticate has an expiration. For CI/CD, generate a fresh token at the start of each pipeline run.
- **Least privilege**: Use KeyForge team/permission features to scope the token to only the credentials the Terraform workspace needs.
