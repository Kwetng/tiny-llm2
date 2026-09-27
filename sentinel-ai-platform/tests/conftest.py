import os, sys, tempfile
from pathlib import Path

os.environ.setdefault("SENTINEL_STATE_DIR", tempfile.mkdtemp(prefix="sentinel-test-"))
for k in ("TYPESAFE_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "GOOGLE_CLOUD_PROJECT", "GOOGLE_ACCESS_TOKEN"):
    os.environ.pop(k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
