#!/usr/bin/env bash
# deploy.sh - puts the Jev + mini LLM fraud scorer on Google Cloud, one numbered step at a time.
#
# Run it from the jev-fraud-detection folder, step by step (recommended the first time):
#     source gcp/deploy.sh          # loads the settings and the step functions
#     step1_project                 # then run step1_..., step2_..., in order, checking the output of each
# or all at once:
#     bash gcp/deploy.sh all
#
# Every step matches a section of the guide (docs/fraud-guide.md, part C).
# Nothing here has been run against a real Google Cloud account by the author: read each command before you run it.

# ---------- settings: change these ----------------------------------------------------------------
PROJECT_ID="${PROJECT_ID:-my-fraud-demo-123}"     # a new, empty project is best for learning
REGION="${REGION:-europe-west2}"                    # London, so data stays in the UK
BUCKET="${BUCKET:-${PROJECT_ID}-fraud-models}"      # bucket names are global: the project id makes it unique
TAG="${TAG:-v1}"                                     # image version
# ---------------------------------------------------------------------------------------------------

IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/fraud/fraud-scorer:${TAG}"
SA_RUN="fraud-scorer@${PROJECT_ID}.iam.gserviceaccount.com"      # identity of the scoring service
SA_PUSH="pubsub-push@${PROJECT_ID}.iam.gserviceaccount.com"      # identity Pub/Sub uses to call the service
SA_TRAIN="fraud-retrain@${PROJECT_ID}.iam.gserviceaccount.com"   # identity of the weekly retraining job
SA_SCHED="scheduler@${PROJECT_ID}.iam.gserviceaccount.com"       # identity Cloud Scheduler uses to start it

step1_project() {             # C2: point gcloud at the project and switch on the services we use
  gcloud config set project "$PROJECT_ID"
  gcloud config set run/region "$REGION"
  gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
    secretmanager.googleapis.com bigquery.googleapis.com pubsub.googleapis.com storage.googleapis.com \
    cloudscheduler.googleapis.com logging.googleapis.com monitoring.googleapis.com
}

step2_identities() {          # C3: one service account per job, each with only the rights it needs
  gcloud iam service-accounts create fraud-scorer --display-name="Fraud scorer (Cloud Run service)"
  gcloud iam service-accounts create pubsub-push --display-name="Pub/Sub push to the fraud scorer"
  gcloud iam service-accounts create fraud-retrain --display-name="Fraud model weekly retraining job"
  gcloud iam service-accounts create scheduler --display-name="Cloud Scheduler trigger"
}

step3_jev_key() {             # C4: keep the Jev API key in Secret Manager, never in code or env files
  if [ -z "${TYPESAFE_API_KEY:-}" ]; then
    echo "No TYPESAFE_API_KEY in this shell: skipping. The service will use the offline stand-in (NOT Jev)."; return
  fi
  printf '%s' "$TYPESAFE_API_KEY" | gcloud secrets create typesafe-api-key --data-file=- \
    --replication-policy=user-managed --locations="$REGION"
  gcloud secrets add-iam-policy-binding typesafe-api-key \
    --member="serviceAccount:${SA_RUN}" --role="roles/secretmanager.secretAccessor"
}

step4_storage() {             # C5: a bucket for model bundles and the BigQuery audit tables
  gcloud storage buckets create "gs://${BUCKET}" --location="$REGION" --uniform-bucket-level-access
  gcloud storage cp gcp/model_bundle/* "gs://${BUCKET}/bundles/initial/"
  gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" --member="serviceAccount:${SA_RUN}" --role="roles/storage.objectViewer"
  gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" --member="serviceAccount:${SA_TRAIN}" --role="roles/storage.objectAdmin"
  bq --location="$REGION" mk --dataset --description="Fraud scorer audit log" "${PROJECT_ID}:fraud"
  bq mk --table --time_partitioning_field=decided_at --description="One row per fraud decision" \
    "${PROJECT_ID}:fraud.decisions" gcp/bigquery_schema.json
  bq mk --table --description="Analysts' verdicts on HOLDs and BLOCKs" "${PROJECT_ID}:fraud.outcomes" gcp/outcomes_schema.json
  bq add-iam-policy-binding --member="serviceAccount:${SA_RUN}" --role="roles/bigquery.dataEditor" "${PROJECT_ID}:fraud.decisions"
}

step5_build() {               # C6: build the container in the cloud and store it in Artifact Registry
  gcloud artifacts repositories create fraud --repository-format=docker --location="$REGION" \
    --description="Fraud scorer images"
  gcloud builds submit --config gcp/cloudbuild.yaml --substitutions="_REGION=${REGION},_TAG=${TAG}" .
}

step6_deploy() {              # C7: run the container on Cloud Run as a private web service
  local secret_flags=(--set-env-vars="BQ_TABLE=${PROJECT_ID}.fraud.decisions,TORCH_THREADS=2,BUNDLE_URI=gs://${BUCKET}/bundles/initial")
  if gcloud secrets describe typesafe-api-key >/dev/null 2>&1; then
    secret_flags+=(--set-secrets="TYPESAFE_API_KEY=typesafe-api-key:latest")
  else
    secret_flags=(--set-env-vars="BQ_TABLE=${PROJECT_ID}.fraud.decisions,TORCH_THREADS=2,BUNDLE_URI=gs://${BUCKET}/bundles/initial,JEV_OFFLINE=true")
  fi
  gcloud run deploy fraud-scorer --image="$IMAGE" --region="$REGION" --service-account="$SA_RUN" \
    --no-allow-unauthenticated --cpu=2 --memory=2Gi --min-instances=0 --max-instances=5 --concurrency=20 \
    --timeout=15 "${secret_flags[@]}"
  gcloud run services add-iam-policy-binding fraud-scorer --region="$REGION" \
    --member="user:$(gcloud config get-value account)" --role="roles/run.invoker"
  SERVICE_URL="$(gcloud run services describe fraud-scorer --region="$REGION" --format='value(status.url)')"
  echo "Service URL: ${SERVICE_URL}"
}

step7_test() {                # C8: send transactions and read the answers
  SERVICE_URL="$(gcloud run services describe fraud-scorer --region="$REGION" --format='value(status.url)')"
  curl -s -H "Authorization: Bearer $(gcloud auth print-identity-token)" "${SERVICE_URL}/healthz"; echo
  curl -s -X POST -H "Authorization: Bearer $(gcloud auth print-identity-token)" -H "Content-Type: application/json" \
    -d @gcp/sample_transaction.json "${SERVICE_URL}/score"; echo
  python gcp/send_test_transactions.py "$SERVICE_URL"
}

step8_pubsub() {              # C9: let other systems send transactions as messages instead of HTTP calls
  SERVICE_URL="$(gcloud run services describe fraud-scorer --region="$REGION" --format='value(status.url)')"
  gcloud pubsub topics create transactions
  gcloud run services add-iam-policy-binding fraud-scorer --region="$REGION" \
    --member="serviceAccount:${SA_PUSH}" --role="roles/run.invoker"
  gcloud pubsub subscriptions create transactions-to-scorer --topic=transactions \
    --push-endpoint="${SERVICE_URL}/pubsub" --push-auth-service-account="$SA_PUSH" --ack-deadline=30
  gcloud pubsub topics publish transactions --message="$(cat gcp/sample_transaction.json)"
}

step9_audit() {               # C10: read the audit log in BigQuery and Cloud Logging
  bq query --use_legacy_sql=false \
    "SELECT decided_at, transaction_id, action, ROUND(risk, 3) AS risk, reason_codes
     FROM \`${PROJECT_ID}.fraud.decisions\` ORDER BY decided_at DESC LIMIT 10"
  gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="fraud-scorer" AND jsonPayload.message="fraud_decision"' \
    --limit=5 --format='table(timestamp, jsonPayload.action, jsonPayload.risk, jsonPayload.latency_ms)'
}

step10_monitoring() {         # C11: a counter of BLOCK decisions that alerts can watch
  gcloud logging metrics create fraud_blocks --description="Number of BLOCK decisions" \
    --log-filter='resource.type="cloud_run_revision" AND resource.labels.service_name="fraud-scorer" AND jsonPayload.message="fraud_decision" AND jsonPayload.action="BLOCK"'
  echo "Now create the alert policies in the console: Monitoring > Alerting > Create policy (see the guide, C11)."
}

step11_retraining() {         # C12: a weekly job that trains a new model bundle for review
  gcloud run jobs create fraud-retrain --image="$IMAGE" --region="$REGION" --service-account="$SA_TRAIN" \
    --command=python --args=retrain.py --set-env-vars="BUNDLE_BUCKET=gs://${BUCKET}" \
    --cpu=2 --memory=4Gi --task-timeout=30m --max-retries=1
  gcloud run jobs add-iam-policy-binding fraud-retrain --region="$REGION" \
    --member="serviceAccount:${SA_SCHED}" --role="roles/run.invoker"
  gcloud scheduler jobs create http fraud-retrain-weekly --location="$REGION" \
    --schedule="0 2 * * 1" --time-zone="Europe/London" --http-method=POST \
    --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/fraud-retrain:run" \
    --oauth-service-account-email="$SA_SCHED"
  echo "To run it now: gcloud run jobs execute fraud-retrain --region=${REGION} --wait"
}

promote() {                   # C13: point the live service at a reviewed bundle, e.g.  promote 2026-10-05-0200
  gcloud run services update fraud-scorer --region="$REGION" --update-env-vars="BUNDLE_URI=gs://${BUCKET}/bundles/$1"
}

cleanup() {                   # C15: delete everything this script created (the bucket and tables too!)
  gcloud scheduler jobs delete fraud-retrain-weekly --location="$REGION" --quiet
  gcloud run jobs delete fraud-retrain --region="$REGION" --quiet
  gcloud pubsub subscriptions delete transactions-to-scorer --quiet
  gcloud pubsub topics delete transactions --quiet
  gcloud run services delete fraud-scorer --region="$REGION" --quiet
  gcloud logging metrics delete fraud_blocks --quiet
  bq rm -r -f "${PROJECT_ID}:fraud"
  gcloud storage rm -r "gs://${BUCKET}"
  gcloud artifacts repositories delete fraud --location="$REGION" --quiet
  gcloud secrets delete typesafe-api-key --quiet 2>/dev/null || true
  for sa in "$SA_RUN" "$SA_PUSH" "$SA_TRAIN" "$SA_SCHED"; do gcloud iam service-accounts delete "$sa" --quiet; done
}

if [ "${1:-}" = "all" ]; then
  set -euo pipefail
  step1_project; step2_identities; step3_jev_key; step4_storage; step5_build; step6_deploy
  step7_test; step8_pubsub; step9_audit; step10_monitoring; step11_retraining
fi
