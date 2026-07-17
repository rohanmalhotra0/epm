"""Local secret storage (spec section 12).

Preference order, degrading gracefully:
  1. OS keychain (optional ``keyring``; unavailable inside most containers)
  2. Encrypted local store (Fernet) under ``<data>/secrets/secrets.enc``  <-- default
  3. Process memory for the current session (passwords that must not persist)

Raw passwords are never written to SQLite. Values stored here are also
registered with the redactor so they can never leak into logs or errors.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
from pathlib import Path

from cryptography.fernet import Fernet

from .redaction import register_secret


def _derive_key(passphrase: str) -> bytes:
    digest = hashlib.sha256(passphrase.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


class EncryptedSecretStore:
    """Fernet-encrypted JSON blob on local disk."""

    def __init__(self, secrets_dir: Path, master_key: str = "") -> None:
        self._dir = secrets_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = secrets_dir / "secrets.enc"
        self._lock = threading.RLock()
        self._fernet = Fernet(self._resolve_key(master_key))

    def _resolve_key(self, master_key: str) -> bytes:
        if master_key:
            return _derive_key(master_key)
        key_path = self._dir / "master.key"
        if key_path.exists():
            return key_path.read_bytes().strip()
        key = Fernet.generate_key()
        key_path.write_bytes(key)
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        return key

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            raw = self._fernet.decrypt(self._path.read_bytes())
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        token = self._fernet.encrypt(json.dumps(data).encode("utf-8"))
        tmp = self._path.with_suffix(".tmp")
        tmp.write_bytes(token)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(self._path)

    def set(self, namespace: str, key: str, value: str) -> None:
        with self._lock:
            data = self._load()
            data.setdefault(namespace, {})[key] = value
            self._save(data)
        register_secret(value)

    def get(self, namespace: str, key: str) -> str | None:
        with self._lock:
            value = self._load().get(namespace, {}).get(key)
        if value:
            register_secret(value)
        return value

    def delete(self, namespace: str, key: str) -> None:
        with self._lock:
            data = self._load()
            if namespace in data and key in data[namespace]:
                del data[namespace][key]
                if not data[namespace]:
                    del data[namespace]
                self._save(data)

    def has(self, namespace: str, key: str) -> bool:
        with self._lock:
            return key in self._load().get(namespace, {})

    def list_keys(self, namespace: str) -> list[str]:
        with self._lock:
            return sorted(self._load().get(namespace, {}).keys())


class ProcessSecretCache:
    """In-memory only. Used for passwords kept for the current session and
    removed as soon as practical (spec section 13, step 7)."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._lock = threading.RLock()

    def _k(self, namespace: str, key: str) -> str:
        return f"{namespace}::{key}"

    def set(self, namespace: str, key: str, value: str) -> None:
        with self._lock:
            self._data[self._k(namespace, key)] = value
        register_secret(value)

    def get(self, namespace: str, key: str) -> str | None:
        with self._lock:
            return self._data.get(self._k(namespace, key))

    def delete(self, namespace: str, key: str) -> None:
        with self._lock:
            self._data.pop(self._k(namespace, key), None)

    def has(self, namespace: str, key: str) -> bool:
        with self._lock:
            return self._k(namespace, key) in self._data
