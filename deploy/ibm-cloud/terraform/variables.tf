variable "prefix" {
  description = "Name prefix for every resource."
  type        = string
  default     = "epmw"
}

variable "region" {
  description = "IBM Cloud VPC region (must also offer watsonx.ai, e.g. us-south, eu-de)."
  type        = string
  default     = "us-south"
}

variable "enable_vpn" {
  description = <<-EOT
    Provision the Client-to-Site VPN server. Default OFF: the recommended
    access design is the Code Engine public HTTPS endpoint with App ID (OIDC)
    in front — nothing to install on a locked-down corporate laptop. Turn this
    on only if you want private-endpoint-only access, in which case
    vpn_server_cert_crn and vpn_client_ca_crn become required.
  EOT
  type        = bool
  default     = false
}

variable "vpn_client_cidr" {
  description = "Address pool handed to VPN clients; must not overlap the subnet. Only used when enable_vpn = true."
  type        = string
  default     = "192.168.8.0/22"
}

variable "vpn_server_cert_crn" {
  description = "Secrets Manager CRN of the VPN server certificate. Required when enable_vpn = true."
  type        = string
  default     = ""
}

variable "vpn_client_ca_crn" {
  description = "Secrets Manager CRN of the CA used to sign VPN client certificates. Required when enable_vpn = true."
  type        = string
  default     = ""
}

variable "enable_postgres" {
  description = "Provision IBM Cloud Databases for PostgreSQL for the backend (wired via the EPMW_DATABASE_URL secret). Off by default: SQLite on the data volume."
  type        = bool
  default     = false
}

variable "enable_gpu_training" {
  description = "Provision the GPU training instance (hourly cost — enable only for the run)."
  type        = bool
  default     = false
}

variable "gpu_profile" {
  description = "VPC GPU profile: gx3-24x120x1l4 (L4), gx3-48x240x2l40s (L40S), gx3d-* (H100)."
  type        = string
  default     = "gx3-24x120x1l4"
}

variable "gpu_image_name" {
  description = "Boot image for the training instance."
  type        = string
  default     = "ibm-ubuntu-24-04-minimal-amd64-1"
}

variable "ssh_key_name" {
  description = "Name of an existing VPC SSH key (required when enable_gpu_training)."
  type        = string
  default     = ""
}

variable "enable_app_id" {
  description = "Provision App ID (managed OAuth/OIDC) as the public front door. The recommended default."
  type        = bool
  default     = true
}

variable "app_id_plan" {
  description = "App ID plan: graduated-tier (free for the first ~1,000 monthly active users) or lite where still available."
  type        = string
  default     = "graduated-tier"
}

variable "auth_redirect_urls" {
  description = "OIDC redirect URLs for the oauth2-proxy app, e.g. [\"https://epmw-auth.....codeengine.appdomain.cloud/oauth2/callback\"]. Usually registered post-deploy by ../configure-app-id.sh instead."
  type        = list(string)
  default     = []
}
