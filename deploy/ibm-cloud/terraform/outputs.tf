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

output "gpu_training_ip" {
  description = "Private IP of the GPU training instance (null unless enable_gpu_training = true)."
  value       = try(ibm_is_instance.gpu_training[0].primary_network_interface[0].primary_ip[0].address, null)
}
