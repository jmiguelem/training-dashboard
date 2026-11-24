output "ip" {
  value = google_compute_address.ip.address
}

output "site_host" {
  description = "Hostname Caddy gets a certificate for."
  value       = local.site_host
}

output "site_url" {
  value = "https://${local.site_host}"
}

output "instance" {
  value = google_compute_instance.vm.name
}

output "zone" {
  value = var.zone
}

output "project_id" {
  value = var.project_id
}

output "backup_bucket" {
  value = google_storage_bucket.backups.name
}
