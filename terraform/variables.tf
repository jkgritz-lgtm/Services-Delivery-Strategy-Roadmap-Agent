variable "project_id" {
  description = "Google Cloud Project ID hosting Vertex AI Agent Engine and Gemini Enterprise"
  type        = string
}

variable "region" {
  description = "Default GCP region for Vertex AI Agent Engine resources"
  type        = string
  default     = "us-central1"
}
