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

variable "environment" {
  description = "Environment label applied to billable application resources"
  type        = string
  default     = "production"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_-]{0,62}$", var.environment))
    error_message = "environment must be a lowercase GCP label value of 1-63 characters."
  }
}

variable "cost_center" {
  description = "Cost-center label used to attribute billable resources"
  type        = string
  default     = "personal"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_-]{0,62}$", var.cost_center))
    error_message = "cost_center must be a lowercase GCP label value of 1-63 characters."
  }
}

variable "billing_account_id" {
  description = "Optional Cloud Billing account ID; when set, creates a monthly project budget"
  type        = string
  default     = ""
}

variable "monthly_budget_amount" {
  description = "Monthly project budget in whole units of budget_currency"
  type        = number
  default     = 50

  validation {
    condition     = var.monthly_budget_amount > 0 && floor(var.monthly_budget_amount) == var.monthly_budget_amount
    error_message = "monthly_budget_amount must be a positive whole number."
  }
}

variable "budget_currency" {
  description = "ISO 4217 currency code for the monthly budget; must match the billing account currency"
  type        = string
  default     = "USD"

  validation {
    condition     = can(regex("^[A-Z]{3}$", var.budget_currency))
    error_message = "budget_currency must be a three-letter uppercase ISO 4217 code."
  }
}

variable "cost_alert_email" {
  description = "Optional email recipient for budget threshold alerts"
  type        = string
  default     = ""
}

variable "iap_authorized_email" {
  description = "Google account email allowed through IAP"
  type        = string
}

variable "drive_folder_id" {
  description = "Google Drive folder ID containing Takeout Archive ZIPs"
  type        = string
}
