from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from datetime import datetime
from azure.storage.blob import BlobServiceClient
import os
import logging

# ---------------------------
# Configuration
# ---------------------------

# Read configuration from environment variables (Azure App Settings)
STORAGE_ACCOUNT_URL = os.getenv("STORAGE_ACCOUNT_URL")
IMAGES_CONTAINER = os.getenv("IMAGES_CONTAINER", "lanternfly-images")
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

# Safety check for missing configuration
if not AZURE_STORAGE_CONNECTION_STRING:
    raise RuntimeError("Missing AZURE_STORAGE_CONNECTION_STRING environment variable.")
if not STORAGE_ACCOUNT_URL:
    raise RuntimeError("Missing STORAGE_ACCOUNT_URL environment variable.")

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/gif"}

# ---------------------------
# Setup
# ---------------------------
logging.basicConfig(level=logging.INFO)

# Initialize Azure Blob clients
bsc = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
cc = bsc.get_container_client(IMAGES_CONTAINER)

# Ensure the container exists and has public blob access
try:
    cc.create_container(public_access="blob")
except Exception:
    pass  # Container likely already exists

app = Flask(__name__)

# ---------------------------
# Routes
# ---------------------------

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/v1/health")
def health():
    return jsonify(ok=True)


@app.post("/api/v1/upload")
def upload():
    try:
        if "file" not in request.files:
            return jsonify(ok=False, error="Missing file field"), 400

        f = request.files["file"]
        if f.filename == "":
            return jsonify(ok=False, error="Empty filename"), 400

        if f.mimetype not in ALLOWED_CONTENT_TYPES:
            return jsonify(ok=False, error=f"Unsupported content type: {f.mimetype}"), 400

        # Enforce file size limit
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(0)
        if size > MAX_FILE_SIZE:
            return jsonify(ok=False, error="File too large (max 10 MB)"), 400

        # Safe and unique blob name
        safe_name = secure_filename(f.filename)
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        blob_name = f"{timestamp}-{safe_name}"

        # Upload to Azure Blob Storage
        cc.upload_blob(
            name=blob_name,
            data=f,
            overwrite=True,
            content_type=f.mimetype
        )

        blob_url = f"{STORAGE_ACCOUNT_URL}/{IMAGES_CONTAINER}/{blob_name}"
        logging.info(f"Uploaded image: {blob_url}")

        return jsonify(ok=True, url=blob_url), 200

    except Exception as e:
        logging.error(f"Upload error: {e}")
        return jsonify(ok=False, error=str(e)), 500


@app.get("/api/v1/gallery")
def gallery():
    try:
        blobs = cc.list_blobs()
        urls = [f"{STORAGE_ACCOUNT_URL}/{IMAGES_CONTAINER}/{b.name}" for b in blobs]
        return jsonify(ok=True, gallery=urls), 200
    except Exception as e:
        logging.error(f"Gallery error: {e}")
        return jsonify(ok=False, error=str(e)), 500


# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    app.run(debug=True)
