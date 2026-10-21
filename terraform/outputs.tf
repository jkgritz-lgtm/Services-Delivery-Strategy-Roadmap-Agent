output "agent_service_account_email" {
  description = "Service account email for the GCC Service Delivery Strategy Agent"
  value       = google_service_account.agent_runtime_sa.email
}

output "staging_bucket_uri" {
  description = "GCS Staging Bucket URI for Vertex AI Agent Engine deployment"
  value       = "gs://${google_storage_bucket.agent_staging_bucket.name}"
}
