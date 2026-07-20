# Deploying EPM Wizard on IBM Cloud

The full architecture — service mapping, request flow, access design, and
the two AI-training paths — is in [`docs/IBM_CLOUD.md`](../../docs/IBM_CLOUD.md);
the end-to-end training runbook is [`docs/TRAINING.md`](../../docs/TRAINING.md).
This directory holds the executable pieces.

## Layout

```
deploy/ibm-cloud/
├── terraform/               VPC, COS, ICR, Code Engine
│   ├── main.tf              project, optional VPN, optional GPU training instance
│   ├── variables.tf         toggles: enable_vpn (default false), enable_gpu_training
│   └── outputs.tf
├── deploy-code-engine.sh    build → push to ICR → create/update the apps
│                            (+ the epmw-auth App ID login gate when configured)
├── configure-app-id.sh      one-time: register the oauth2 callback in App ID
├── upload_corpus.sh         create the COS bucket + upload training JSONL files
└── training/                GPU (Path B) QLoRA kit — runs on the VSI, not the app
```

## 1. Provision infrastructure

```bash
cd deploy/ibm-cloud/terraform
export IC_API_KEY=<ibm-cloud-api-key>

terraform init
terraform apply
```

No VPN certificates needed by default: `enable_vpn = false`, and the access
design is the Code Engine **public HTTPS endpoint with App ID (OIDC) in
front** — browser-only, nothing to install on a corporate laptop.

For a private-endpoint-only topology instead:

```bash
terraform apply \
  -var enable_vpn=true \
  -var vpn_server_cert_crn=crn:...:secret:... \
  -var vpn_client_ca_crn=crn:...:secret:...
```

The two CRNs are certificates from **Secrets Manager** (server certificate,
and the CA that signs client certificates); they are required only when
`enable_vpn = true`. Everything lands in one resource group (`epmw-rg`) so
billing is a single filtered view.

## 2. Deploy the apps

```bash
# one-time: the backend's secret bundle (watsonx key, Oracle creds)
ibmcloud ce secret create --name epmw-secrets --from-env-file .env.production

REGION=us-south ICR_NAMESPACE=epmw CE_PROJECT=epmw-project \
  ./deploy-code-engine.sh
```

Re-run the script to roll out a new image; it updates in place.

**App ID login gate (recommended before sharing the URL):** terraform already
provisioned App ID (`enable_app_id=true` default). Create the `epmw-appid`
secret from the terraform outputs (exact command in the comments of
`deploy-code-engine.sh`), re-run the deploy script — it deploys the
`epmw-auth` oauth2-proxy app as the only public endpoint and flips the
frontend to project visibility — then run `./configure-app-id.sh` once to
register the callback URL. Without the secret the frontend stays public with
no login (fine for a quick demo, not for real data). Set
`FRONTEND_VISIBILITY=private` for the VPN topology instead.

**Optional managed database**: with `terraform apply -var enable_postgres=true`
(outputs `postgres_host`/`postgres_port`), create a service key for the
instance, then put `EPMW_DATABASE_URL` in a Code Engine secret named
`epmw-database` (override via `DB_SECRET`). The deploy script injects it when
the secret exists; otherwise the backend stays on SQLite on the `/data` volume.
Database tier trade-offs are in `docs/IBM_CLOUD.md` §4.

## 3. Train on your EPM data

Follow [`docs/TRAINING.md`](../../docs/TRAINING.md) — corpus build (synthetic
+ real export), `./upload_corpus.sh`, Tuning Studio (Path A) or the
[`training/`](training/) GPU kit (Path B, `-var enable_gpu_training=true`),
and the eval bake-off that gates the switch. Destroy the GPU instance when
the run finishes (`-var enable_gpu_training=false` + apply).

## 4. Invite a user

Default topology: send the **App ID** email invite (cloud directory). They
open the public URL in a browser and sign in — done.

VPN topology only: additionally send the OpenVPN client profile from the VPN
server's client page; they connect to the VPN and open the private URL.
