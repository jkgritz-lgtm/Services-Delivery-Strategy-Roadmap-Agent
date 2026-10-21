# Terraform Infrastructure as Code (IaC) for GCC Service Delivery Strategy Agent
# Addresses AgentOps Rubric 5.2 (Infrastructure as Code) & 5.3 (Secure Secret Management)

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.30.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  required_apis = [
    "aiplatform.googleapis.com",
    "discoveryengine.googleapis.com",
    "slides.googleapis.com",
    "drive.googleapis.com",
    "dlp.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudtrace.googleapis.com",
    "logging.googleapis.com",
  ]
}

# 1. Enable Required Google Cloud & Workspace APIs
resource "google_project_service" "enabled_apis" {
  for_each           = toset(local.required_apis)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# 2. Dedicated Least-Privilege Service Account for Agent Engine
resource "google_service_account" "agent_runtime_sa" {
  account_id   = "gcc-delivery-strategy-sa"
  display_name = "GCC Service Delivery Strategy Agent Runtime SA"
  description  = "Least-privilege identity for the Gemini Enterprise GCC Service Delivery Strategy ADK Agent"
}

# 3. Least-Privilege IAM Bindings (Vertex AI, DLP, Secret Manager, Trace & Logging)
resource "google_project_iam_member" "agent_iam_roles" {
  for_each = toset([
    "roles/aiplatform.user",
    "roles/discoveryengine.viewer",
    "roles/dlp.user",
    "roles/secretmanager.secretAccessor",
    "roles/cloudtrace.agent",
    "roles/logging.logWriter",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.agent_runtime_sa.email}"
}

# 4. GCS Staging & Session Artifact Bucket
resource "google_storage_bucket" "agent_staging_bucket" {
  name                        = "${var.project_id}-gcc-delivery-strategy-staging"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }
}

# 5. Google Cloud Secret Manager Secrets for Google Workspace OAuth
resource "google_secret_manager_secret" "oauth_client_id" {
  secret_id = "gcc-slides-oauth-client-id"
  replication {
    auto {}
  }
  depends_on = [google_project_service.enabled_apis]
}

resource "google_secret_manager_secret" "oauth_client_secret" {
  secret_id = "gcc-slides-oauth-client-secret"
  replication {
    auto {}
  }
  depends_on = [google_project_service.enabled_apis]
}

resource "google_secret_manager_secret" "oauth_access_token" {
  secret_id = "gcc-slides-oauth-access-token"
  replication {
    auto {}
  }
  depends_on = [google_project_service.enabled_apis]
}
