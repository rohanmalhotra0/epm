"""Connector boundary + validation + redaction tests (spec sections 12, 14)."""

from __future__ import annotations

import pytest

from app.connector import DemoConnector
from app.connector.errors import InvalidArgument
from app.connector.validation import validate_filename, validate_rule_name
from app.security.redaction import (
    REDACTION,
    looks_like_secret,
    redact_mapping,
    redact_text,
    register_secret,
)


async def test_demo_connector_metadata():
    c = DemoConnector()
    assert [a.name for a in await c.list_applications()] == ["MCWPCF"]
    cubes = await c.list_cubes("MCWPCF")
    assert {"OEP_FS", "OEP_WFP", "OEP_DCSH", "OEP_REP"} <= {x.name for x in cubes}


async def test_demo_run_rule_and_verify_loop():
    c = DemoConnector()
    job = await c.run_business_rule("MCWPCF", "OEP_FS", "IR", {"Scenario": "Forecast"})
    assert job.status == "completed"
    from app.connector.demo import register_deployed_form
    register_deployed_form("MCWPCF", {"name": "My Form", "application": "MCWPCF", "cube": "OEP_FS", "folder": "x"})
    assert (await c.verify_form("MCWPCF", "My Form")) is not None


async def test_unknown_rule_raises():
    c = DemoConnector()
    from app.connector.errors import ConnectorError
    with pytest.raises(ConnectorError):
        await c.run_business_rule("MCWPCF", None, "Nonexistent", {})


def test_command_injection_is_rejected():
    for bad in ["rm -rf /; echo", "a | b", "$(whoami)", "a`b`", "../etc/passwd"]:
        with pytest.raises(InvalidArgument):
            validate_rule_name(bad)


def test_filename_rejects_traversal():
    with pytest.raises(InvalidArgument):
        validate_filename("../secret.zip")
    assert validate_filename("form_123.zip") == "form_123.zip"


def test_redaction_scrubs_patterns_and_registered_secrets():
    register_secret("hunter2password")
    text = "authorization: Bearer abc123def456ghi and password=topsecret and hunter2password"
    out = redact_text(text)
    assert REDACTION in out
    assert "hunter2password" not in out
    assert "topsecret" not in out


def test_redact_mapping_sensitive_keys():
    out = redact_mapping({"password": "p", "note": "ok", "apiKey": "sk-xxxxxxxxxxxxxxxx"})
    assert out["password"] == REDACTION
    assert out["note"] == "ok"


def test_looks_like_secret():
    assert looks_like_secret("my key is sk-ant-abcdefghijklmnop")
    assert looks_like_secret("password=supersecret")
    assert not looks_like_secret("create an actuals form")


def test_redaction_closes_known_bypasses():
    # credentials in a URL whose username is an email address (contains '@')
    url = "https://Rohanm@ibm.com:Mestro365!@host.oraclecloud.com/api"
    out = redact_text(url)
    assert "Mestro365!" not in out and "Rohanm@ibm.com" not in out
    assert out.startswith("https://") and "host.oraclecloud.com/api" in out
    # common token formats beyond the OpenAI/Anthropic/AWS set. Every synthetic
    # token here is assembled from parts so no literal matches a real-secret
    # scanner (the Slack `xoxb-` shape otherwise trips GitHub secret scanning).
    for token in ("ghp_" + "a" * 36,
                  "xoxb-" + "1" * 12 + "-" + "a" * 16,
                  "eyJhbGciOi." + "a" * 8 + "." + "b" * 8):
        assert REDACTION in redact_text(f"secret is {token}")


def test_redact_mapping_matches_prefixed_keys():
    out = redact_mapping({"db_password": "x1234567", "oracle_secret": "y1234567", "author": "Jane Doe"})
    assert out["db_password"] == REDACTION
    assert out["oracle_secret"] == REDACTION
    assert out["author"] == "Jane Doe"  # benign key must not be over-redacted
