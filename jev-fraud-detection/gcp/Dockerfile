# Build from the jev-fraud-detection folder:
#   docker build -f gcp/Dockerfile -t fraud-scorer .
#   gcloud builds submit --config gcp/cloudbuild.yaml .
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY gcp/service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY code/jev_client.py code/fraud_jev_llm.py gcp/service/scorer.py gcp/service/main.py gcp/service/retrain.py ./
COPY gcp/model_bundle ./model_bundle
RUN useradd --create-home --uid 10001 scorer
USER scorer
# Cloud Run sends traffic to $PORT; one worker per container, Cloud Run adds containers under load
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
