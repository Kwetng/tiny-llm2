"""Tests for the Cloud Run scoring service. No Google Cloud account, API key or network needed.

    pip install -r gcp/service/requirements.txt pytest httpx
    pytest -q tests
"""
import base64, json, os, sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
os.environ["BUNDLE_DIR"] = str(ROOT / "gcp" / "model_bundle")
os.environ["JEV_OFFLINE"] = "true"
os.environ.pop("BQ_TABLE", None)
sys.path[:0] = [str(ROOT / "gcp" / "service"), str(ROOT / "code")]

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

client = TestClient(main.app)
SAMPLES = json.load(open(ROOT / "gcp" / "model_bundle" / "samples.json"))


def test_health():
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert "not Jev" in r.json()["decision_model"]          # the stand-in is always labelled


@pytest.mark.parametrize("s", SAMPLES, ids=[s["name"] for s in SAMPLES])
def test_service_matches_the_batch_pipeline(s):
    """The service must give exactly the decision the batch pipeline gave for the same transaction."""
    d = client.post("/score", json=s["transaction"]).json()
    e = s["expected"]
    assert d["action"] == e["action"]
    assert d["risk"] == pytest.approx(e["risk"], abs=1e-3)
    assert d["p_challenger"] == pytest.approx(e["p_challenger"], abs=1e-3)
    assert d["llm_surprise_bits"] == pytest.approx(e["surprise_bits"], abs=1e-2)
    assert d["overrides"] == e["overrides"]
    assert d["reason_codes"] and d["decision_id"]


def test_step_up_gets_the_fixed_scam_warning():
    s = next(x for x in SAMPLES if x["expected"]["action"] == "STEP-UP")
    msg = client.post("/score", json=s["transaction"]).json()["customer_message"]
    assert msg is not None and "safe account" in msg


def test_pubsub_push():
    tx = SAMPLES[0]["transaction"]
    env = {"message": {"data": base64.b64encode(json.dumps(tx).encode()).decode(), "messageId": "1"}, "subscription": "s"}
    r = client.post("/pubsub", json=env)
    assert r.status_code == 200 and r.json()["status"] == "scored"


def test_bad_pubsub_message_is_acknowledged_not_retried():
    env = {"message": {"data": base64.b64encode(b"not json").decode()}, "subscription": "s"}
    assert client.post("/pubsub", json=env).json()["status"] == "rejected"


def test_invalid_transaction_is_rejected():
    bad = dict(SAMPLES[0]["transaction"], amount=-5)
    assert client.post("/score", json=bad).status_code == 422


def test_mule_list_always_blocks():
    tx = dict(SAMPLES[0]["transaction"], on_mule_list=True)
    d = client.post("/score", json=tx).json()
    assert d["action"] == "BLOCK" and any("mule" in o for o in d["overrides"])


def test_audit_row_matches_the_bigquery_schema(monkeypatch):
    """Every column written must exist in gcp/bigquery_schema.json, and every REQUIRED column must be filled."""
    rows = []

    class FakeBQ:
        def insert_rows_json(self, table, r):
            rows.extend(r)
            return []

    monkeypatch.setattr(main, "BQ_TABLE", "demo.fraud.decisions")
    monkeypatch.setattr(main, "_bq", FakeBQ())
    client.post("/score", json=SAMPLES[2]["transaction"])
    schema = json.load(open(ROOT / "gcp" / "bigquery_schema.json"))
    cols = {c["name"] for c in schema}
    assert rows and set(rows[0]) <= cols
    assert all(rows[0].get(c["name"]) is not None for c in schema if c.get("mode") == "REQUIRED")


def test_bundle_download_from_cloud_storage(monkeypatch, tmp_path):
    """BUNDLE_URI=gs://bucket/bundles/initial must copy every file of that folder, and nothing from other folders."""
    from google.cloud import storage
    src = ROOT / "gcp" / "model_bundle"

    class Blob:
        def __init__(self, name, path=None): self.name, self.path = name, path
        def download_to_filename(self, dest): Path(dest).write_bytes(self.path.read_bytes())

    class Client:
        def list_blobs(self, bucket, prefix):
            assert bucket == "demo-bucket" and prefix == "bundles/initial/"
            return [Blob("bundles/initial/")] + [Blob(f"bundles/initial/{p.name}", p) for p in src.iterdir()]

    monkeypatch.setattr(storage, "Client", Client)
    out = main._download_bundle("gs://demo-bucket/bundles/initial", str(tmp_path / "b"))
    assert sorted(p.name for p in Path(out).iterdir()) == sorted(p.name for p in src.iterdir())
    from scorer import FraudScorer
    assert FraudScorer(out, offline=True).score(SAMPLES[2]["transaction"])["action"] == SAMPLES[2]["expected"]["action"]
