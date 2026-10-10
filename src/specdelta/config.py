"""Settings read from the environment, plus local paths."""

import os
from pathlib import Path

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
REGION = os.environ.get("REGION", "europe-west4")  # BigQuery dataset, Cloud Run
BQ_DATASET = os.environ.get("BQ_DATASET", "specdelta")

# Gemini is called through the global endpoint, which has the widest model availability.
# GOOGLE_CLOUD_LOCATION is also what ADK and the google-genai SDK read for this.
VERTEX_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
FLASH_MODEL = os.environ.get("FLASH_MODEL", "gemini-2.5-flash")
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"  # zips as downloaded from the 3GPP archive
DOCX_DIR = DATA_DIR / "docx"  # unzipped .docx files
PARSED_DIR = DATA_DIR / "parsed"  # clauses/tables as JSONL plus parse reports
EMBEDDINGS_DIR = DATA_DIR / "embeddings"  # one vector per chunk, kept so reruns are free

# The corpus, as 3GPP archive file names. The letter after the dash is the release
# (h = Rel-17, i = Rel-18, j = Rel-19), followed by minor and patch version.
DOCUMENTS = [
    "38300-hh0",
    "38300-ib0",
    "38101-1-hn0",
    "38101-1-if0",
    "38321-hf0",
    "38321-ia0",
    "21905-j20",
]
