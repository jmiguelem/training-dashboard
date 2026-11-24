variable "project_id" {
  description = "GCP project to deploy into."
  type        = string
}

variable "region" {
  description = "us-central1, us-east1 and us-west1 are the regions covered by the e2-micro free tier."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-a"
}

variable "machine_type" {
  description = "e2-micro (1 GB) works with the swap this config adds; use e2-small (2 GB) for faster, safer builds."
  type        = string
  default     = "e2-micro"
}

variable "domain" {
  description = "Your domain, with an A record pointing at the static IP. Empty uses <ip>.sslip.io, which needs no DNS."
  type        = string
  default     = ""
}

variable "name" {
  description = "Prefix for resource names. Change it per app if you share a project."
  type        = string
  default     = "training"
}

variable "data_disk_gb" {
  type    = number
  default = 10
}

variable "backup_retention_days" {
  type    = number
  default = 30
}
