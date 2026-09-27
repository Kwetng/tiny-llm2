"""send_test_transactions.py - sends the six sample transactions to the scorer and prints each decision.

    python gcp/send_test_transactions.py http://localhost:8080          # local service, no login needed
    python gcp/send_test_transactions.py https://fraud-scorer-xxxx.run.app  # Cloud Run: uses your gcloud login

On Cloud Run the service is private, so each request carries an identity token from `gcloud auth print-identity-token`.
"""
import json, subprocess, sys, urllib.request  # nosec B404 - only runs the gcloud CLI with fixed arguments
from pathlib import Path

url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8080"
headers = {"Content-Type": "application/json"}
if url.startswith("https://"):
    token = subprocess.run(["gcloud", "auth", "print-identity-token"],  # nosec B603 B607 - fixed command, no user input
                           capture_output=True, text=True, check=True).stdout.strip()
    headers["Authorization"] = "Bearer " + token
samples = json.load(open(Path(__file__).parent / "model_bundle" / "samples.json"))
for s in samples:
    req = urllib.request.Request(url + "/score", data=json.dumps(s["transaction"]).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:  # nosec B310 - URL given by the operator on the command line
        d = json.load(r)
    print(f"{s['name']:24s} {s['transaction']['description'][:28]:28s} -> {d['action']:8s} risk {d['risk']:.1%} "
          f"(expected {s['expected']['action']}), {d['latency_ms']} ms")
