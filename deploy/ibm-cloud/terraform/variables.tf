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

variable "vpn_client_cidr" {
  description = "Address pool handed to VPN clients; must not overlap the subnet."
  type        = string
  default     = "192.168.8.0/22"
}

variable "vpn_server_cert_crn" {
  description = "Secrets Manager CRN of the VPN server certificate."
  type        = string
}

variable "vpn_client_ca_crn" {
  description = "Secrets Manager CRN of the CA used to sign VPN client certificates."
  type        = string
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
