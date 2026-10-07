resource "google_project_service" "bigquery" {
  project            = var.project_id
  service            = "bigquery.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "bigquerydatatransfer" {
  project            = var.project_id
  service            = "bigquerydatatransfer.googleapis.com"
  disable_on_destroy = false
}

resource "google_bigquery_dataset" "billing_export" {
  project       = var.project_id
  dataset_id    = "${replace(var.project_id, "-", "_")}_billing_export"
  friendly_name = "TheBoss Photos billing export"
  description   = "Destination for detailed Cloud Billing exports used for cost analysis."
  location      = "US"
  labels        = local.cost_labels

  depends_on = [google_project_service.bigquery]
}

resource "google_project_service" "monitoring" {
  count = var.billing_account_id != "" && var.cost_alert_email != "" ? 1 : 0

  project            = var.project_id
  service            = "monitoring.googleapis.com"
  disable_on_destroy = false
}

resource "google_monitoring_notification_channel" "cost_alert_email" {
  count = var.billing_account_id != "" && var.cost_alert_email != "" ? 1 : 0

  project      = var.project_id
  display_name = "TheBoss Photos cost alerts"
  type         = "email"
  labels = {
    email_address = var.cost_alert_email
  }

  depends_on = [google_project_service.monitoring]
}

resource "google_billing_budget" "project_monthly" {
  count = var.billing_account_id != "" ? 1 : 0

  billing_account = var.billing_account_id
  display_name    = "${var.project_id} monthly cost budget"

  budget_filter {
    projects        = ["projects/${data.google_project.project.number}"]
    calendar_period = "MONTH"
  }

  amount {
    specified_amount {
      currency_code = var.budget_currency
      units         = tostring(var.monthly_budget_amount)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }

  threshold_rules {
    threshold_percent = 0.8
  }

  threshold_rules {
    threshold_percent = 1.0
  }

  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  all_updates_rule {
    monitoring_notification_channels = var.cost_alert_email == "" ? [] : [
      google_monitoring_notification_channel.cost_alert_email[0].id
    ]
    disable_default_iam_recipients  = var.cost_alert_email != ""
    enable_project_level_recipients = var.cost_alert_email == ""
  }
}
