output "vpn_server_id" {
  description = "Client-to-Site VPN server id (null unless enable_vpn = true)."
  value       = try(ibm_is_vpn_server.epmw[0].id, null)
}

output "code_engine_project_id" {
  description = "Pass to ../deploy-code-engine.sh via CE_PROJECT."
  value       = ibm_code_engine_project.epmw.id
}

output "training_bucket" {
  description = "COS bucket for the fine-tuning corpus (scripts/export_training_data.py output)."
  value       = ibm_cos_bucket.training.bucket_name
}

output "registry_namespace" {
  value = ibm_cr_namespace.epmw.name
}

output "postgres_host" {
  description = "Private hostname of the PostgreSQL instance (null when enable_postgres is false)."
  value       = try(data.ibm_database_connection.postgres[0].postgres[0].hosts[0].hostname, null)
}

output "postgres_port" {
  description = "Port of the PostgreSQL instance (null when enable_postgres is false)."
  value       = try(data.ibm_database_connection.postgres[0].postgres[0].hosts[0].port, null)
}

output "gpu_training_ip" {
  description = "Private IP of the GPU training instance (null unless enable_gpu_training = true)."
  value       = try(ibm_is_instance.gpu_training[0].primary_network_interface[0].primary_ip[0].address, null)
}
