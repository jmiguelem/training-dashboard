locals {
  site_host = var.domain != "" ? var.domain : "${replace(google_compute_address.ip.address, ".", "-")}.sslip.io"
}

resource "google_project_service" "apis" {
  for_each           = toset(["compute.googleapis.com", "iap.googleapis.com", "storage.googleapis.com"])
  service            = each.key
  disable_on_destroy = false
}

resource "google_compute_address" "ip" {
  name       = "${var.name}-ip"
  depends_on = [google_project_service.apis]
}

# Web traffic from anywhere; SSH only through Google's IAP tunnel, so port 22 is never open to the internet.
resource "google_compute_firewall" "web" {
  name          = "${var.name}-web"
  network       = "default"
  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["${var.name}-web"]
  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }
  allow {
    protocol = "udp"
    ports    = ["443"]
  }
  depends_on = [google_project_service.apis]
}

resource "google_compute_firewall" "iap_ssh" {
  name          = "${var.name}-iap-ssh"
  network       = "default"
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["${var.name}-web"]
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  depends_on = [google_project_service.apis]
}

# The database and Garmin tokens live here, apart from the VM, so rebuilding or replacing the VM keeps them.
resource "google_compute_disk" "data" {
  name       = "${var.name}-data"
  type       = "pd-standard"
  size       = var.data_disk_gb
  depends_on = [google_project_service.apis]

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_storage_bucket" "backups" {
  name                        = "${var.project_id}-${var.name}-backups"
  location                    = upper(var.region)
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  lifecycle_rule {
    condition {
      age = var.backup_retention_days
    }
    action {
      type = "Delete"
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_service_account" "vm" {
  account_id   = "${var.name}-vm"
  display_name = "${var.name} VM"
}

resource "google_storage_bucket_iam_member" "vm_backups" {
  bucket = google_storage_bucket.backups.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_compute_instance" "vm" {
  name         = var.name
  machine_type = var.machine_type
  tags         = ["${var.name}-web"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 20
      type  = "pd-standard"
    }
  }

  attached_disk {
    source      = google_compute_disk.data.id
    device_name = "data"
  }

  network_interface {
    network = "default"
    access_config {
      nat_ip = google_compute_address.ip.address
    }
  }

  service_account {
    email  = google_service_account.vm.email
    scopes = ["cloud-platform"] # actual access is limited by the IAM roles above
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  metadata_startup_script = templatefile("${path.module}/startup.sh.tftpl", {
    bucket = google_storage_bucket.backups.name
  })

  allow_stopping_for_update = true
  depends_on                = [google_project_service.apis]
}
