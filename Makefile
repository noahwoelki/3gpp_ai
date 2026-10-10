# Project ID, region etc. come from .env (see .env.example)
-include .env
export

export UV_DEFAULT_INDEX := https://pypi.org/simple
unexport UV_INDEX_URL
export NPM_CONFIG_REGISTRY := https://registry.npmjs.org/

.PHONY: sync lint test download parse describe embed load search ask dev-agent dev-api dev-web build-web diff setup-gcp deploy logs

sync:
	uv sync

lint:
	uv run ruff check src tests scripts
	uv run ruff format --check src tests scripts

test:
	uv run pytest

# Fetch missing spec zips into data/raw/ and unzip them into data/docx/
download:
	uv run python -m specdelta.ingest.download

# Parse every spec into clauses, then chunks, typed tables and glossary, all in data/parsed/
parse:
	uv run python -m specdelta.ingest.parse_docx
	uv run python -m specdelta.ingest.chunk
	uv run python -m specdelta.ingest.tables
	uv run python -m specdelta.ingest.glossary

# Describe large tables with Gemini (only tables without a description yet)
describe:
	uv run python -m specdelta.ingest.describe_tables

# Embed all searchable chunks (only chunks without a vector yet)
embed:
	uv run python -m specdelta.ingest.embed

# Load clauses, chunks, tables and glossary into BigQuery (replaces the tables)
load:
	uv run python -m specdelta.ingest.load_bigquery

# Hybrid search from the command line, e.g. make search Q="cell DTX" ARGS="--release Rel-18"
search:
	uv run python -m specdelta.search.hybrid "$(Q)" $(ARGS)

# Ask the agents one question in the terminal, e.g. make ask Q="What is SSB-less SCell?"
ask:
	uv run python scripts/ask.py "$(Q)"

# ADK dev UI on http://localhost:8000
dev-agent:
	uv run adk web src/specdelta/agents

# API server on http://localhost:8080 (also serves the built UI from web/dist)
dev-api:
	uv run uvicorn specdelta.api:app --reload --port 8080

# React dev server on http://localhost:5173, forwards /api to the API server
dev-web:
	cd web && npm run dev

build-web:
	cd web && npm ci && npm run build

# Compare Rel-17 and Rel-18 of a spec, e.g. make diff SPEC=38.300 CLAUSE=15.4
diff:
	uv run python -m specdelta.diff.clause_diff $(SPEC) $(CLAUSE) --show

# --- Google Cloud deployment ---------------------------------------------------------

SERVICE := specdelta
SERVICE_ACCOUNT := specdelta-run@$(GOOGLE_CLOUD_PROJECT).iam.gserviceaccount.com

# One-time setup: a service account for the app with only the rights it needs
setup-gcp:
	gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
	gcloud iam service-accounts describe $(SERVICE_ACCOUNT) >/dev/null 2>&1 || \
		gcloud iam service-accounts create specdelta-run --display-name="SpecDelta Cloud Run"
	@# A new service account takes a few seconds until IAM accepts role bindings for it
	@until gcloud iam service-accounts describe $(SERVICE_ACCOUNT) >/dev/null 2>&1; do sleep 3; done
	@sleep 10
	for role in roles/bigquery.dataViewer roles/bigquery.jobUser roles/aiplatform.user roles/discoveryengine.viewer; do \
		gcloud projects add-iam-policy-binding $(GOOGLE_CLOUD_PROJECT) --condition=None --quiet \
			--member=serviceAccount:$(SERVICE_ACCOUNT) --role=$$role >/dev/null; \
	done

# Build the container with Cloud Build and deploy it to Cloud Run. The service is public,
# anyone with the URL can use it. max-instances caps how much can run at the same time.
deploy:
	gcloud run deploy $(SERVICE) --source . --region $(REGION) \
		--service-account $(SERVICE_ACCOUNT) --allow-unauthenticated \
		--memory 2Gi --cpu 1 --timeout 300 --min-instances 0 --max-instances 2 \
		--set-env-vars GOOGLE_CLOUD_PROJECT=$(GOOGLE_CLOUD_PROJECT),GOOGLE_CLOUD_LOCATION=$(GOOGLE_CLOUD_LOCATION),GOOGLE_GENAI_USE_VERTEXAI=TRUE,REGION=$(REGION),BQ_DATASET=$(BQ_DATASET),FLASH_MODEL=$(FLASH_MODEL)

logs:
	gcloud beta run services logs tail $(SERVICE) --region $(REGION)
