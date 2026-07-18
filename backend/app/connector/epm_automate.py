"""Restricted local EPM Automate runner (spec section 15).

Security posture:
  * strict command allowlist — no arbitrary commands
  * subprocess *argument arrays* only — never ``shell=True``, never string interp
  * fixed working directory, execution timeouts, redacted output
  * no generic command endpoint is exposed to the model

Oracle software is never redistributed. The runner invokes an EPM Automate
binary the user has installed/mounted locally (``EPMW_EPMAUTOMATE_PATH``); if it
is absent every method degrades gracefully and diagnostics report it.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from ..config import get_settings
from ..logging import get_logger
from ..security.redaction import redact_text, register_secret
from .errors import ConnectorError, ErrorCategory
from .validation import validate_filename, validate_timeout

log = get_logger(__name__)

# Only these EPM Automate commands may ever be invoked.
ALLOWED_COMMANDS = {
    "login",
    "logout",
    "listfiles",
    "uploadfile",
    "downloadfile",
    "importsnapshot",
    "exportsnapshot",
    "exportmetadata",
    "runbusinessrule",
    "getsubstvar",
    "feedback",
    "version",
}


class EpmAutomateRunner:
    def __init__(self) -> None:
        settings = get_settings()
        self.binary = settings.epmautomate_path
        self.workdir = settings.runner_dir
        self.metadata_job = settings.oracle_metadata_job
        self.java_home = settings.java_home
        self.workdir.mkdir(parents=True, exist_ok=True)

    @property
    def installed(self) -> bool:
        return bool(self.binary) and Path(self.binary).exists()

    async def run(self, command: str, args: list[str], timeout: int = 300) -> tuple[int, str, str]:
        if command not in ALLOWED_COMMANDS:
            raise ConnectorError(
                ErrorCategory.security,
                f"Command '{command}' is not allowlisted.",
                suggested_action="Only a fixed set of EPM Automate commands are permitted.",
            )
        validate_timeout(timeout)
        if not self.installed:
            raise ConnectorError(
                ErrorCategory.epm_automate,
                "EPM Automate is not installed or not configured.",
                likely_cause="EPMW_EPMAUTOMATE_PATH is unset or the binary is missing.",
                suggested_action="Install/mount EPM Automate locally and set EPMW_EPMAUTOMATE_PATH, or use Demo Mode.",
            )
        # Every argument is a discrete list element — never joined into a shell string.
        argv = [self.binary, command, *[str(a) for a in args]]
        env = {**os.environ}
        # epmautomate.sh requires JAVA_HOME; inject the configured one so the app
        # doesn't depend on the ambient shell environment.
        if self.java_home:
            env["JAVA_HOME"] = self.java_home
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(self.workdir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError as exc:
            raise ConnectorError(
                ErrorCategory.timeout,
                f"EPM Automate '{command}' timed out after {timeout}s.",
            ) from exc
        except FileNotFoundError as exc:
            raise ConnectorError(ErrorCategory.epm_automate, "EPM Automate binary could not be launched.") from exc
        out = redact_text(out_b.decode("utf-8", "replace"))
        err = redact_text(err_b.decode("utf-8", "replace"))
        log.info("epmautomate", command=command, returncode=proc.returncode)
        return proc.returncode, out, err

    async def login(self, url: str, username: str, password: str) -> bool:
        register_secret(password)
        # EPM Automate login takes the password (or an encrypted file) as an arg.
        rc, _out, err = await self.run("login", [username, password, url])
        if rc != 0:
            raise ConnectorError(
                ErrorCategory.authentication,
                "EPM Automate login failed.",
                technical_detail=err,
                suggested_action="Check the URL, username and password, then retry.",
            )
        return True

    async def upload_file(self, local_path: str, remote_name: str) -> None:
        validate_filename(remote_name)
        rc, _out, err = await self.run("uploadfile", [local_path])
        if rc != 0:
            raise ConnectorError(ErrorCategory.upload, "Upload failed.", technical_detail=err)

    async def export_metadata(self, job_name: str, file_name: str, timeout: int = 600) -> None:
        """Run a saved 'Export Metadata' job, writing the export to ``file_name`` in
        the tenant outbox. ``job_name`` is a tenant-configured artifact name, not a
        path — only the file name is filename-validated."""
        validate_filename(file_name)
        rc, _out, err = await self.run("exportmetadata", [job_name, file_name], timeout=timeout)
        if rc != 0:
            raise ConnectorError(ErrorCategory.epm_automate, "Metadata export failed.", technical_detail=err,
                                 suggested_action="Confirm the Export Metadata job name exists in the application.")

    async def download_file(self, remote_name: str, timeout: int = 300) -> Path:
        """Download a tenant file into the runner workdir and return its local path."""
        validate_filename(remote_name)
        rc, _out, err = await self.run("downloadfile", [remote_name], timeout=timeout)
        if rc != 0:
            raise ConnectorError(ErrorCategory.epm_automate, "Download failed.", technical_detail=err)
        local = self.workdir / remote_name
        if not local.exists():
            raise ConnectorError(ErrorCategory.epm_automate,
                                 f"Downloaded file '{remote_name}' was not found in the runner directory.")
        return local

    def diagnostics(self) -> dict:
        java = shutil.which("java") or (os.path.join(os.environ.get("JAVA_HOME", ""), "bin", "java")
                                        if os.environ.get("JAVA_HOME") else None)
        writable = os.access(self.workdir, os.W_OK)
        return {
            "epmAutomateInstalled": self.installed,
            "epmAutomatePath": self.binary or None,
            "javaFound": bool(java),
            "javaPath": java,
            "workdir": str(self.workdir),
            "workdirWritable": writable,
            "allowedCommands": sorted(ALLOWED_COMMANDS),
            # Member import readiness: needs both the binary AND a saved export job.
            "metadataExportJobConfigured": bool(self.metadata_job),
            "memberImportReady": self.installed and bool(self.metadata_job),
        }
