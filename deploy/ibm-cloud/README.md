# Deploying EPM Wizard on IBM Cloud

The full architecture — service mapping, request flow, VPN invite flow, and
the two AI-training paths — is in [`docs/IBM_CLOUD.md`](../../docs/IBM_CLOUD.md).
This directory holds the executable pieces.

## Layout

```
deploy/ibm-cloud/
├── terraform/               VPC, Client-to-Site VPN, COS, ICR, Code Engine
│   ├── main.tf              project, optional GPU training instance
│   ├── variables.tf
│   └── outputs.tf
└── deploy-code-engine.sh    build → push to ICR → create/update the two apps
```

## 1. Provision infrastructure

```bash
cd deploy/ibm-cloud/terraform
export IC_API_KEY=<ibm-cloud-api-key>

terraform init
terraform apply \
  -var vpn_server_cert_crn=crn:...:secret:... \
  -var vpn_client_ca_crn=crn:...:secret:...
```

The two CRNs are certificates from **Secrets Manager** (server certificate,
and the CA that signs client certificates). Everything lands in one resource
group (`epmw-rg`) so billing is a single filtered view.

## 2. Deploy the apps

```bash
# one-time: the backend's secret bundle (watsonx key, Oracle creds)
ibmcloud ce secret create --name epmw-secrets --from-env-file .env.production

REGION=us-south ICR_NAMESPACE=epmw CE_PROJECT=epmw-project \
  ./deploy-code-engine.sh
```

Re-run the script to roll out a new image; it updates in place.

## 3. Train on your EPM data

```bash
cd backend
python -m scripts.export_training_data --out data/training/epm-tuning.jsonl
ibmcloud cos upload --bucket epmw-training-data \
  --key epm-tuning.jsonl --file data/training/epm-tuning.jsonl
```

Then either tune in **watsonx.ai Tuning Studio** (managed) or set
`-var enable_gpu_training=true -var ssh_key_name=<key>` and fine-tune on the
GPU instance — details and trade-offs in `docs/IBM_CLOUD.md` §3. Destroy the
GPU instance when the run finishes (`-var enable_gpu_training=false` + apply).

## 4. Invite a user

1. **App ID**: send the email invite (cloud directory).
2. Send the OpenVPN client profile from the VPN server's client page.
3. They connect to the VPN and open the private URL.
