# EPM Wizard — all-IBM infrastructure skeleton (see docs/IBM_CLOUD.md).
#
# Provisions: VPC + private subnet, Client-to-Site VPN server, Cloud Object
# Storage (training corpora), Container Registry namespace, a Code Engine
# project, and an optional GPU training instance. The Code Engine *apps* are
# created/updated by ../deploy-code-engine.sh so image rollouts don't require
# a terraform run.
#
# This is a reviewed starting point, not a turnkey production module: bring
# your own certificate CRNs (Secrets Manager) and harden to taste.

terraform {
  required_version = ">= 1.5"
  required_providers {
    ibm = {
      source  = "IBM-Cloud/ibm"
      version = ">= 1.70"
    }
  }
}

provider "ibm" {
  region = var.region
  # Authenticates via the IC_API_KEY environment variable.
}

resource "ibm_resource_group" "epmw" {
  name = "${var.prefix}-rg"
}

# ---- Network: VPC + private subnet ------------------------------------------

resource "ibm_is_vpc" "epmw" {
  name           = "${var.prefix}-vpc"
  resource_group = ibm_resource_group.epmw.id
}

resource "ibm_is_subnet" "private" {
  name                     = "${var.prefix}-subnet"
  vpc                      = ibm_is_vpc.epmw.id
  zone                     = "${var.region}-1"
  total_ipv4_address_count = 256
  resource_group           = ibm_resource_group.epmw.id
}

resource "ibm_is_security_group" "app" {
  name           = "${var.prefix}-app-sg"
  vpc            = ibm_is_vpc.epmw.id
  resource_group = ibm_resource_group.epmw.id
}

# Only VPN clients may reach the app tier (VPN topology only). With the
# default enable_vpn = false the front door is the Code Engine public HTTPS
# endpoint with App ID (OIDC) in front, so this rule is not created.
resource "ibm_is_security_group_rule" "app_from_vpn" {
  count     = var.enable_vpn ? 1 : 0
  group     = ibm_is_security_group.app.id
  direction = "inbound"
  remote    = var.vpn_client_cidr
  tcp {
    port_min = 443
    port_max = 443
  }
}

resource "ibm_is_security_group_rule" "app_egress" {
  group     = ibm_is_security_group.app.id
  direction = "outbound"
  remote    = "0.0.0.0/0" # outbound HTTPS to Oracle EPM Cloud + watsonx.ai
}

# ---- Optional: Client-to-Site VPN -------------------------------------------
# Default OFF (enable_vpn = false): access is the Code Engine public HTTPS
# endpoint with App ID in front, which works from a corporate laptop with
# nothing installed. Enable only for private-endpoint-only topologies; both
# certificate CRNs (Secrets Manager) are then required.

resource "ibm_is_vpn_server" "epmw" {
  count           = var.enable_vpn ? 1 : 0
  name            = "${var.prefix}-vpn"
  certificate_crn = var.vpn_server_cert_crn
  client_ip_pool  = var.vpn_client_cidr
  subnets         = [ibm_is_subnet.private.id]
  security_groups = [ibm_is_security_group.app.id]
  resource_group  = ibm_resource_group.epmw.id

  client_authentication {
    method        = "certificate"
    client_ca_crn = var.vpn_client_ca_crn
  }

  lifecycle {
    precondition {
      condition     = var.vpn_server_cert_crn != "" && var.vpn_client_ca_crn != ""
      error_message = "enable_vpn = true requires both vpn_server_cert_crn and vpn_client_ca_crn (Secrets Manager certificate CRNs)."
    }
  }
}

# ---- Cloud Object Storage: training corpora + artifact backups --------------

resource "ibm_resource_instance" "cos" {
  name              = "${var.prefix}-cos"
  service           = "cloud-object-storage"
  plan              = "standard"
  location          = "global"
  resource_group_id = ibm_resource_group.epmw.id
}

resource "ibm_cos_bucket" "training" {
  bucket_name          = "${var.prefix}-training-data"
  resource_instance_id = ibm_resource_instance.cos.id
  region_location      = var.region
  storage_class        = "smart"
}

# ---- Container Registry + Code Engine ---------------------------------------

resource "ibm_cr_namespace" "epmw" {
  name              = var.prefix
  resource_group_id = ibm_resource_group.epmw.id
}

resource "ibm_code_engine_project" "epmw" {
  name              = "${var.prefix}-project"
  resource_group_id = ibm_resource_group.epmw.id
}

# ---- Optional: IBM Cloud Databases for PostgreSQL (docs/IBM_CLOUD.md §4) ----
# For multi-instance / team deployments the backend swaps SQLite for a managed
# PostgreSQL via EPMW_DATABASE_URL — see ../deploy-code-engine.sh. Smallest
# standard-plan allocation, private endpoint only (reachable from Code Engine
# and the VPN, never the public internet).
#
# Credentials are a deliberate manual step (they stay out of Terraform state):
#   ibmcloud resource service-key-create "${var.prefix}-pg-creds" \
#     --instance-name "${var.prefix}-pg"
# then build EPMW_DATABASE_URL from the key (host/port below, user + password
# from the key, sslmode=verify-full + the ICD CA cert) and store it in the
# epmw-database Code Engine secret.

resource "ibm_database" "postgres" {
  count             = var.enable_postgres ? 1 : 0
  name              = "${var.prefix}-pg"
  service           = "databases-for-postgresql"
  plan              = "standard"
  location          = var.region
  resource_group_id = ibm_resource_group.epmw.id
  service_endpoints = "private"

  # Smallest viable allocation (per-member; ICD minimums as of provider 1.70).
  group {
    group_id = "member"
    memory {
      allocation_mb = 4096
    }
    disk {
      allocation_mb = 5120
    }
    cpu {
      allocation_count = 0 # shared CPU — cheapest tier
    }
  }
}

data "ibm_database_connection" "postgres" {
  count         = var.enable_postgres ? 1 : 0
  deployment_id = ibm_database.postgres[0].id
  user_type     = "database"
  user_id       = "admin"
  endpoint_type = "private"
}

# ---- Optional: GPU-as-a-Service training instance (docs/IBM_CLOUD.md §3.3) --
# Hourly-billed and expensive: enable for the training run, then set the
# toggle back to false and apply to destroy it.

data "ibm_is_image" "training" {
  count = var.enable_gpu_training ? 1 : 0
  name  = var.gpu_image_name
}

data "ibm_is_ssh_key" "training" {
  count = var.enable_gpu_training ? 1 : 0
  name  = var.ssh_key_name
}

resource "ibm_is_instance" "gpu_training" {
  count          = var.enable_gpu_training ? 1 : 0
  name           = "${var.prefix}-gpu-train"
  vpc            = ibm_is_vpc.epmw.id
  zone           = "${var.region}-1"
  profile        = var.gpu_profile
  image          = data.ibm_is_image.training[0].id
  keys           = [data.ibm_is_ssh_key.training[0].id]
  resource_group = ibm_resource_group.epmw.id

  primary_network_interface {
    subnet          = ibm_is_subnet.private.id
    security_groups = [ibm_is_security_group.app.id]
  }
}

# ---- App ID (managed OAuth/OIDC front door; docs/IBM_CLOUD.md §5) -----------
# The default access design: an oauth2-proxy Code Engine app (created by
# ../deploy-code-engine.sh) sits in front of the frontend and authenticates
# against this App ID instance. Users are invited in the App ID dashboard
# (Cloud Directory) or via an identity federation you configure there.

resource "ibm_resource_instance" "app_id" {
  count             = var.enable_app_id ? 1 : 0
  name              = "${var.prefix}-appid"
  service           = "appid"
  plan              = var.app_id_plan
  location          = var.region
  resource_group_id = ibm_resource_group.epmw.id
}

resource "ibm_appid_application" "web" {
  count     = var.enable_app_id ? 1 : 0
  tenant_id = ibm_resource_instance.app_id[0].guid
  name      = "${var.prefix}-web"
  type      = "regularwebapp"
}

# The oauth2-proxy callback URL is only known after the first Code Engine
# deploy (its URL is generated). Run ../configure-app-id.sh after deploying
# to register it, or re-apply with auth_redirect_urls set explicitly.
resource "ibm_appid_redirect_urls" "web" {
  count     = var.enable_app_id && length(var.auth_redirect_urls) > 0 ? 1 : 0
  tenant_id = ibm_resource_instance.app_id[0].guid
  urls      = var.auth_redirect_urls
}
