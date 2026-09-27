output "gateway_url" {
  value = google_cloud_run_v2_service.gateway.uri
}

output "gateway_service_account" {
  value = google_service_account.gateway.email
}

output "audit_bucket" {
  value = google_storage_bucket.audit.name
}
