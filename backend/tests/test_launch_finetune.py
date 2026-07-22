"""Fine-tune launcher: payload building, preflight guards, dry-run safety,
and the launch/status flows against a fake Together client (no network)."""

from __future__ import annotations

import json

import pytest

from scripts.launch_finetune import (
    FinetuneConfig,
    TogetherClient,
    _normalize_job,
    build_job_payload,
    build_parser,
    count_examples,
    poll_until_terminal,
    resolve_api_key,
    run,
)


def _parse(*argv: str):
    return build_parser().parse_args(list(argv))


def _write_corpus(path, n: int) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for i in range(n):
            fh.write(json.dumps({"messages": [
                {"role": "user", "content": f"q{i}"},
                {"role": "assistant", "content": f"a{i}"},
            ]}) + "\n")


class FakeClient:
    """Same three-method surface as TogetherClient, all in-memory."""

    def __init__(self, *, statuses=None) -> None:
        self.uploaded: list[str] = []
        self.created: list[dict] = []
        self._statuses = list(statuses or ["completed"])

    def upload_file(self, path, purpose="fine-tune") -> str:
        self.uploaded.append(path.name)
        return f"file-{path.name}"

    def create_finetune(self, payload) -> dict:
        self.created.append(payload)
        return {"id": "ft-xyz", "status": "pending"}

    def get_finetune(self, job_id) -> dict:
        status = self._statuses.pop(0) if len(self._statuses) > 1 else self._statuses[0]
        return {"id": job_id, "status": status, "output_name": "acct/epm-coder"}


# ---- pure helpers ----------------------------------------------------------

def test_build_job_payload_lora_and_validation():
    cfg = FinetuneConfig(base_model="Base/Model", suffix="epm")
    payload = build_job_payload("file-train", cfg, "file-val")
    assert payload["training_file"] == "file-train"
    assert payload["validation_file"] == "file-val"
    assert payload["model"] == "Base/Model"
    assert payload["lora"] is True and payload["lora_r"] == 16
    assert payload["suffix"] == "epm"


def test_build_job_payload_full_finetune_omits_lora_and_val():
    payload = build_job_payload("file-train", FinetuneConfig(lora=False))
    assert "lora" not in payload
    assert "validation_file" not in payload


def test_resolve_api_key_prefers_explicit(monkeypatch):
    monkeypatch.setenv("TOGETHER_API_KEY", "env-key")
    assert resolve_api_key("explicit") == "explicit"
    assert resolve_api_key(None) == "env-key"
    monkeypatch.delenv("TOGETHER_API_KEY")
    assert resolve_api_key(None) is None


def test_count_examples_ignores_blank_lines(tmp_path):
    path = tmp_path / "c.jsonl"
    path.write_text('{"a":1}\n\n{"b":2}\n\n')
    assert count_examples(path) == 2


class _Enum:
    def __init__(self, value):
        self.value = value


class _Resp:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_normalize_job_handles_object_and_enum_status():
    job = _normalize_job(_Resp(id="ft-1", status=_Enum("completed"),
                               output_name="acct/model"))
    assert job == {"id": "ft-1", "status": "completed", "output_name": "acct/model"}


def test_normalize_job_handles_plain_dict_and_missing_fields():
    job = _normalize_job({"id": "ft-2", "status": "running"})
    assert job == {"id": "ft-2", "status": "running", "output_name": None}


def test_client_raises_helpful_error_when_sdk_missing(monkeypatch):
    # Simulate the optional 'together' package not being installed.
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "together":
            raise ImportError("no module named together")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(SystemExit, match="finetune"):
        TogetherClient("some-key")


# ---- dry run (default, no network, no cost) --------------------------------

def test_dry_run_does_not_touch_client(tmp_path, monkeypatch):
    corpus = tmp_path / "train.jsonl"
    _write_corpus(corpus, 20)
    # Any accidental client construction would blow up loudly.
    monkeypatch.setattr("scripts.launch_finetune.TogetherClient",
                        lambda *a, **k: pytest.fail("dry run must not build a client"))
    summary = run(_parse("--train", str(corpus)))
    assert summary["action"] == "dry-run"
    assert summary["examples"] == 20
    assert "no cost" in summary["note"]
    # The previewed payload uses placeholders, not real uploaded ids.
    assert summary["jobPayload"]["training_file"] == "<uploaded-training-file>"


def test_preflight_rejects_tiny_corpus(tmp_path):
    corpus = tmp_path / "train.jsonl"
    _write_corpus(corpus, 3)
    with pytest.raises(SystemExit, match="below the"):
        run(_parse("--train", str(corpus)))


def test_force_allows_tiny_corpus_dry_run(tmp_path):
    corpus = tmp_path / "train.jsonl"
    _write_corpus(corpus, 3)
    summary = run(_parse("--train", str(corpus), "--force"))
    assert summary["examples"] == 3


# ---- launch (billable path, faked client) ----------------------------------

def test_launch_uploads_and_creates_job(tmp_path, monkeypatch):
    corpus = tmp_path / "train.jsonl"
    val = tmp_path / "val.jsonl"
    _write_corpus(corpus, 50)
    _write_corpus(val, 5)
    fake = FakeClient()
    monkeypatch.setattr("scripts.launch_finetune.TogetherClient", lambda *a, **k: fake)

    summary = run(_parse("--train", str(corpus), "--val", str(val),
                         "--launch", "--api-key", "k"))

    assert summary["action"] == "launch"
    assert fake.uploaded == ["train.jsonl", "val.jsonl"]
    assert summary["jobId"] == "ft-xyz"
    # The created job references the real uploaded file ids, not placeholders.
    assert fake.created[0]["training_file"] == "file-train.jsonl"
    assert fake.created[0]["validation_file"] == "file-val.jsonl"


def test_launch_without_key_errors(tmp_path, monkeypatch):
    monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
    corpus = tmp_path / "train.jsonl"
    _write_corpus(corpus, 50)
    with pytest.raises(SystemExit, match="TOGETHER_API_KEY"):
        run(_parse("--train", str(corpus), "--launch"))


def test_follow_polls_until_terminal():
    fake = FakeClient(statuses=["running", "running", "completed"])
    job = poll_until_terminal(fake, "ft-1", interval=0, sleep=lambda _s: None)
    assert job["status"] == "completed"


def test_status_lookup(monkeypatch):
    fake = FakeClient(statuses=["running"])
    monkeypatch.setattr("scripts.launch_finetune.TogetherClient", lambda *a, **k: fake)
    summary = run(_parse("--status", "ft-1", "--api-key", "k"))
    assert summary == {"action": "status", "jobId": "ft-1",
                       "status": "running", "outputName": "acct/epm-coder"}


def test_build_generates_synthetic_corpus(tmp_path, monkeypatch):
    """--build with no --train generates a corpus, then dry-runs on it."""
    out = tmp_path / "synthetic.jsonl"
    monkeypatch.setattr("scripts.launch_finetune.DEFAULT_TRAIN_PATH", str(out))
    monkeypatch.setattr("scripts.launch_finetune.TogetherClient",
                        lambda *a, **k: pytest.fail("dry run must not build a client"))
    summary = run(_parse("--build"))
    assert summary["action"] == "dry-run"
    assert summary["examples"] > 0
    assert out.exists()
    assert "corpusBuild" in summary
