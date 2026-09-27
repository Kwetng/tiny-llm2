# Sentinel AI Platform - Google Cloud landing zone (europe-west2, London).
# Vertex AI / Gemini behind a VPC Service Controls perimeter, CMEK everywhere, a least-privilege
# service account for the gateway, and audit logs in a locked-retention bucket.

terraform {
  required_version = ">= 1.7"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 6.0" }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  name   = "${var.prefix}-${var.environment}"
  labels = merge(var.labels, { environment = var.environment, workload = "sentinel-ai-gateway", data_class = "confidential" })
}

resource "google_project_service" "apis" {
  for_each = toset(["aiplatform.googleapis.com", "cloudkms.googleapis.com", "run.googleapis.com", "vpcaccess.googleapis.com",
                    "accesscontextmanager.googleapis.com", "logging.googleapis.com", "discoveryengine.googleapis.com"])
  service            = each.value
  disable_on_destroy = false
}

# ---------------------------------------------------------------- keys
resource "google_kms_key_ring" "ai" {
  name     = "kr-${local.name}"
  location = var.region
}

resource "google_kms_crypto_key" "ai_data" {
  name            = "cmk-ai-data"
  key_ring        = google_kms_key_ring.ai.id
  rotation_period = "7776000s" # 90 days
  purpose         = "ENCRYPT_DECRYPT"
  version_template {
    algorithm        = "GOOGLE_SYMMETRIC_ENCRYPTION"
    protection_level = "HSM"
  }
  lifecycle { prevent_destroy = true }
}

data "google_project" "this" {}

resource "google_kms_crypto_key_iam_member" "vertex_uses_cmk" {
  crypto_key_id = google_kms_crypto_key.ai_data.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-aiplatform.iam.gserviceaccount.com"
}

resource "google_kms_crypto_key_iam_member" "storage_uses_cmk" {
  crypto_key_id = google_kms_crypto_key.ai_data.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gs-project-accounts.iam.gserviceaccount.com"
}

# ---------------------------------------------------------------- network
resource "google_compute_network" "ai" {
  name                    = "vpc-${local.name}"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "ai" {
  name                     = "snet-${local.name}"
  ip_cidr_range            = var.subnet_cidr
  region                   = var.region
  network                  = google_compute_network.ai.id
  private_ip_google_access = true
  log_config {
    aggregation_interval = "INTERVAL_5_SEC"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

resource "google_compute_firewall" "deny_all_ingress" {
  name      = "fw-${local.name}-deny-ingress"
  network   = google_compute_network.ai.id
  direction = "INGRESS"
  priority  = 65534
  deny { protocol = "all" }
  source_ranges = ["0.0.0.0/0"]
}

# ---------------------------------------------------------------- service perimeter
resource "google_access_context_manager_service_perimeter" "ai" {
  parent = "accessPolicies/${var.access_policy_id}"
  name   = "accessPolicies/${var.access_policy_id}/servicePerimeters/${replace(local.name, "-", "_")}_ai"
  title  = "${local.name} AI perimeter"
  status {
    resources           = ["projects/${data.google_project.this.number}"]
    restricted_services = ["aiplatform.googleapis.com", "storage.googleapis.com", "discoveryengine.googleapis.com", "cloudkms.googleapis.com"]
    vpc_accessible_services {
      enable_restriction = true
      allowed_services   = ["RESTRICTED-SERVICES"]
    }
  }
}

# ---------------------------------------------------------------- gateway identity (least privilege)
resource "google_service_account" "gateway" {
  account_id   = "sa-${local.name}-gw"
  display_name = "Sentinel AI gateway"
}

resource "google_project_iam_member" "gateway_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.gateway.email}"
}

# ---------------------------------------------------------------- immutable audit bucket
resource "google_storage_bucket" "audit" {
  name                        = "${var.project_id}-${local.name}-ai-audit"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = local.labels
  versioning { enabled = true }
  encryption { default_kms_key_name = google_kms_crypto_key.ai_data.id }
  retention_policy {
    retention_period = var.audit_retention_days * 86400
    is_locked        = false # lock once the first audit export has been reviewed
  }
  logging { log_bucket = "${var.project_id}-access-logs" }
  depends_on = [google_kms_crypto_key_iam_member.storage_uses_cmk]
}

resource "google_storage_bucket_iam_member" "gateway_writes_audit" {
  bucket = google_storage_bucket.audit.name
  role   = "roles/storage.objectCreator" # append only: the gateway cannot delete or overwrite
  member = "serviceAccount:${google_service_account.gateway.email}"
}

# ---------------------------------------------------------------- Vertex AI settings
resource "google_vertex_ai_endpoint" "private" {
  name         = "sentinel-${var.environment}"
  display_name = "sentinel-${var.environment}"
  location     = var.region
  network      = "projects/${data.google_project.this.number}/global/networks/${google_compute_network.ai.name}"
  labels       = local.labels
  encryption_spec { kms_key_name = google_kms_crypto_key.ai_data.id }
  depends_on = [google_kms_crypto_key_iam_member.vertex_uses_cmk]
}

# ---------------------------------------------------------------- the gateway itself (Cloud Run, internal only)
resource "google_cloud_run_v2_service" "gateway" {
  name                = "sentinel-gateway-${var.environment}"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  deletion_protection = true
  labels              = local.labels
  template {
    service_account = google_service_account.gateway.email
    encryption_key  = google_kms_crypto_key.ai_data.id
    containers {
      image = var.gateway_image
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "VERTEX_REGION"
        value = var.region
      }
      env {
        name  = "VERTEX_MODEL"
        value = var.gemini_model_id # pinned model id
      }
    }
    vpc_access {
      network_interfaces {
        network    = google_compute_network.ai.id
        subnetwork = google_compute_subnetwork.ai.id
      }
      egress = "ALL_TRAFFIC"
    }
  }
}
