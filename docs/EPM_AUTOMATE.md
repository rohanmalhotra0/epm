# EPM Automate (optional, local)

EPM Wizard can drive Oracle **EPM Automate** for snapshot import/export and other
operations. Oracle software is **not redistributed** by this project — you mount
or install EPM Automate locally.

Demo Mode needs none of this.

## Requirements

- A Java runtime (EPM Automate requires Java; version per your EPM Automate build).
- An EPM Automate installation you have licensed access to.

## Configure

Set the binary path so the runner can find it (via `.env` or the environment):

```bash
EPMW_EPMAUTOMATE_PATH=/opt/epmautomate/bin/epmautomate.sh
JAVA_HOME=/usr/lib/jvm/java-11
```

To make it available inside the backend container, mount it in
`docker-compose.yml`:

```yaml
services:
  backend:
    volumes:
      - epmw-data:/data
      - /opt/epmautomate:/opt/epmautomate:ro   # your local install
    environment:
      EPMW_EPMAUTOMATE_PATH: /opt/epmautomate/bin/epmautomate.sh
      JAVA_HOME: /usr/lib/jvm/java-11
```

(The base backend image ships without a JRE to stay slim; add one, or mount a JRE,
if you enable the runner.)

## Safety

The runner (`app/connector/epm_automate.py`) is deliberately restricted:

- **Command allowlist** — only a fixed set of EPM Automate commands may run
  (`login`, `logout`, `listfiles`, `uploadfile`, `downloadfile`, `importsnapshot`,
  `exportsnapshot`, `exportmetadata`, `runbusinessrule`, `getsubstvar`, `feedback`,
  `version`).
- **Argument arrays only** — never `shell=True`, never string interpolation.
- Fixed working directory, execution timeouts, and **output redaction**.
- No public network listener, no generic shell access.

## Diagnostics

The **Diagnostics** page reports Java presence, EPM Automate presence/path, and
whether the working directory is writable. `GET /api/diagnostics` returns the same
data; when EPM Automate is absent, EPM Wizard clearly reports Demo Mode.
