# ─── KeyForge Terraform Provider - Example Usage ─────────────────────────────
#
# This file demonstrates how to configure the KeyForge provider, look up
# existing credentials, create new ones, and inject secrets into downstream
# resources such as AWS Lambda environment variables.
#
# Prerequisites:
#   - A running KeyForge instance (e.g. http://localhost:8000)
#   - A valid JWT token obtained via POST /api/auth/login
# ─────────────────────────────────────────────────────────────────────────────

terraform {
  required_providers {
    keyforge = {
      source  = "keyforge/keyforge"
      version = "~> 1.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ─── Provider Configuration ─────────────────────────────────────────────────

provider "keyforge" {
  host  = var.keyforge_host   # or set KEYFORGE_HOST env var
  token = var.keyforge_token  # or set KEYFORGE_TOKEN env var
}

variable "keyforge_host" {
  type        = string
  default     = "http://localhost:8000"
  description = "URL of the KeyForge API server."
}

variable "keyforge_token" {
  type        = string
  sensitive   = true
  description = "JWT authentication token for KeyForge."
}

# ─── Data Source: look up a single credential by api_name ────────────────────

data "keyforge_credential" "openai" {
  api_name = "openai"
}

# ─── Data Source: look up a single credential by ID ──────────────────────────

data "keyforge_credential" "stripe_by_id" {
  credential_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}

# ─── Data Source: list all production credentials ────────────────────────────

data "keyforge_credentials" "production_secrets" {
  environment = "production"
}

# ─── Resource: create a new credential ───────────────────────────────────────

resource "keyforge_credential" "sendgrid_prod" {
  api_name        = "sendgrid"
  api_key         = var.sendgrid_api_key
  environment     = "production"
  credential_type = "api_key"
}

variable "sendgrid_api_key" {
  type        = string
  sensitive   = true
  description = "SendGrid API key to store in KeyForge."
}

# ─── Resource: create an AWS credential ──────────────────────────────────────

resource "keyforge_credential" "aws_staging" {
  api_name        = "aws"
  api_key         = var.aws_secret_key
  environment     = "staging"
  credential_type = "api_key"
}

variable "aws_secret_key" {
  type        = string
  sensitive   = true
  description = "AWS secret access key to store in KeyForge."
}

# ─── Injecting KeyForge secrets into an AWS Lambda ───────────────────────────
#
# This demonstrates the primary use case: pulling secrets from KeyForge at
# apply time and passing them to other Terraform-managed infrastructure.

resource "aws_lambda_function" "api_worker" {
  function_name = "api-worker"
  runtime       = "python3.12"
  handler       = "handler.main"
  role          = "arn:aws:iam::123456789012:role/lambda-exec"
  filename      = "lambda.zip"

  environment {
    variables = {
      OPENAI_API_KEY  = data.keyforge_credential.openai.api_key
      SENDGRID_KEY    = keyforge_credential.sendgrid_prod.api_key
    }
  }
}

# ─── Outputs ─────────────────────────────────────────────────────────────────

output "openai_credential_status" {
  value       = data.keyforge_credential.openai.status
  description = "Validation status of the OpenAI credential."
}

output "production_credential_count" {
  value       = length(data.keyforge_credentials.production_secrets.credentials)
  description = "Number of production credentials stored in KeyForge."
}

output "sendgrid_credential_id" {
  value       = keyforge_credential.sendgrid_prod.id
  description = "ID of the newly created SendGrid credential in KeyForge."
}
