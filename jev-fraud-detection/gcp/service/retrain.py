"""retrain.py - the weekly retraining job (runs as a Cloud Run job, triggered by Cloud Scheduler).

1. Runs the training pipeline and exports a fresh model bundle.
2. Uploads it to Cloud Storage under a dated folder: gs://BUCKET/bundles/YYYY-MM-DD-HHMM/
3. Does NOT switch the live service over. A person reviews the new model's metrics.json and then
   points the service at the new folder (see the guide: "Promote a new model").

In this demo the pipeline re-creates its synthetic data. With real data, the training step would read
labelled transactions from BigQuery (fraud.decisions joined to fraud.outcomes) instead.
"""
import os, subprocess, sys, time  # nosec B404 - runs our own training script with fixed arguments
from pathlib import Path

from google.cloud import storage

bucket_uri = os.environ["BUNDLE_BUCKET"]                     # e.g. gs://my-project-fraud-models
work = Path("/tmp/retrain"); work.mkdir(parents=True, exist_ok=True)  # nosec B108 - container scratch space
bundle = work / "bundle"
subprocess.run([sys.executable,  # nosec B603 - fixed arguments, no user input
                str(Path(__file__).resolve().parent / "fraud_jev_llm.py"), "--offline", "--export-bundle", str(bundle)],
               cwd=work, check=True)
stamp = time.strftime("%Y-%m-%d-%H%M", time.gmtime())
bucket = storage.Client().bucket(bucket_uri.removeprefix("gs://").rstrip("/"))
for f in list(bundle.iterdir()) + [work / "fraud_outputs" / "metrics.json"]:
    bucket.blob(f"bundles/{stamp}/{f.name}").upload_from_filename(str(f))
print(f"New model bundle uploaded to {bucket_uri.rstrip('/')}/bundles/{stamp}/ - review metrics.json before promoting it")
