variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "photolib-405112"
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "us-central1"
}

variable "iap_authorized_email" {
  description = "Google account email allowed through IAP"
  type        = string
}

variable "drive_folder_id" {
  description = "Google Drive folder ID containing Takeout Archive ZIPs"
  type        = string
}
