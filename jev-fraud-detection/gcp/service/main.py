"""
main.py - the fraud scoring web service that runs on Google Cloud Run.

Endpoints
  GET  /healthz   -> {"status": "ok", ...}          Cloud Run checks this to know the service is up
  POST /score     -> decision for one transaction   called directly by the payment system (real time)
  POST /pubsub    -> same, for a Pub/Sub push       used when transactions arrive as messages on a topic

Settings (environment variables, all optional)
  BUNDLE_DIR       folder with the model bundle (default: ./model_bundle inside the container)
  BUNDLE_URI       gs://bucket/path - if set, the bundle is downloaded from Cloud Storage at start-up
  BQ_TABLE         project.dataset.table - if set, every decision is written to BigQuery (the audit log)
  TYPESAFE_API_KEY Jev API key (on Cloud Run it comes from Secret Manager); without it the stand-in is used
  JEV_OFFLINE      "true" forces the offline stand-in even if a key is present

Run locally:  uvicorn main:app --port 8080     (from gcp/service, after copying the bundle next to it)
"""
import base64, json, logging, os, sys, time, uuid
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

from scorer import FraudScorer

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")
log = logging.getLogger("fraud-scorer")


def _download_bundle(uri, dest):
    from google.cloud import storage
    bucket_name, _, prefix = uri.removeprefix("gs://").partition("/")
    client = storage.Client()
    Path(dest).mkdir(parents=True, exist_ok=True)
    for blob in client.list_blobs(bucket_name, prefix=prefix.rstrip("/") + "/"):
        name = blob.name.rsplit("/", 1)[-1]
        if name:
            blob.download_to_filename(str(Path(dest) / name))
    return dest


BUNDLE_DIR = os.environ.get("BUNDLE_DIR", str(Path(__file__).parent / "model_bundle"))
if os.environ.get("BUNDLE_URI"):
    BUNDLE_DIR = _download_bundle(os.environ["BUNDLE_URI"], "/tmp/model_bundle")  # nosec B108 - container-local scratch
SCORER = FraudScorer(BUNDLE_DIR)
BQ_TABLE = os.environ.get("BQ_TABLE")
_bq = None


class Transaction(BaseModel):
    """One payment plus the customer's context (normally supplied by the bank's feature store)."""
    transaction_id: Optional[str] = Field(None, description="the payment system's own id")
    customer_id: int
    amount: float = Field(..., gt=0, description="amount in GBP")
    channel: Literal["card_present", "card_online", "faster_payment"]
    description: str = Field(..., max_length=140, description="merchant name or the payment reference")
    hour: float = Field(..., ge=0, lt=24, description="local time as a decimal hour, e.g. 14.5")
    abroad: bool
    median: float = Field(..., gt=0, description="this customer's median payment in GBP")
    new_payee: bool
    payee_age: Optional[float] = Field(None, description="days since the payee's account was opened (transfers only)")
    new_device: bool
    password_reset: bool
    mins_since_login: Optional[float] = None
    txns_last_hour: int = Field(..., ge=0)
    unusual_hour: bool
    on_mule_list: bool = False


app = FastAPI(title="Jev + mini LLM fraud scorer", version="1.0")


def _audit(tx, decision):
    """Write the decision to BigQuery (the audit log). Failures are logged, never block the payment."""
    global _bq
    row = {"decision_id": decision["decision_id"], "transaction_id": tx.transaction_id, "customer_id": tx.customer_id,
           "decided_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "amount_gbp": tx.amount, "channel": tx.channel,
           "action": decision["action"], "risk": decision["risk"], "p_jev": decision["p_jev"],
           "jev_fraud_type": decision["jev_fraud_type"], "p_challenger": decision["p_challenger"],
           "llm_surprise_bits": decision["llm_surprise_bits"], "overrides": decision["overrides"],
           "reason_codes": decision["reason_codes"], "decision_model": decision["decision_model"],
           "model_versions": json.dumps(decision["model_versions"]), "input_hash": decision["input_hash"],
           "latency_ms": decision["latency_ms"]}
    log.info(json.dumps({"severity": "INFO", "message": "fraud_decision", **row}))   # always goes to Cloud Logging
    if not BQ_TABLE:
        return
    try:
        if _bq is None:
            from google.cloud import bigquery
            _bq = bigquery.Client()
        errors = _bq.insert_rows_json(BQ_TABLE, [row])
        if errors:
            log.error(json.dumps({"severity": "ERROR", "message": "bigquery_insert_failed", "errors": errors}))
    except Exception as e:  # noqa: BLE001 - the payment decision must never fail because logging failed
        log.error(json.dumps({"severity": "ERROR", "message": "bigquery_unavailable", "error": str(e)}))


def _decide(tx: Transaction):
    decision = SCORER.score(tx.model_dump())
    decision["decision_id"] = str(uuid.uuid4())
    decision["transaction_id"] = tx.transaction_id
    _audit(tx, decision)
    return decision


@app.get("/healthz")
def healthz():
    return {"status": "ok", "decision_model": SCORER.jev.name, "model_versions": SCORER.versions}


@app.post("/score")
def score(tx: Transaction):
    return _decide(tx)


@app.post("/pubsub")
async def pubsub_push(request: Request):
    """Pub/Sub push format: {"message": {"data": base64(json transaction), ...}, "subscription": ...}.
    Returning 2xx acknowledges the message; an error makes Pub/Sub retry it."""
    envelope = await request.json()
    try:
        tx = Transaction(**json.loads(base64.b64decode(envelope["message"]["data"])))
    except Exception as e:  # noqa: BLE001
        # a malformed message will never succeed: acknowledge it and log it instead of retrying forever
        log.error(json.dumps({"severity": "ERROR", "message": "bad_pubsub_message", "error": str(e)}))
        return {"status": "rejected"}
    d = _decide(tx)
    return {"status": "scored", "action": d["action"], "decision_id": d["decision_id"]}

