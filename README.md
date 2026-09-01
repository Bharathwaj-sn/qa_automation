# Data Health Monitor API

Minimal FastAPI + Streamlit POC for Databricks Unity Catalog metadata inspection.

## Architecture

- Streamlit frontend calls the FastAPI API
- FastAPI routes delegate to a Databricks service
- Databricks service uses the Databricks SDK `WorkspaceClient`
- Unity Catalog metadata is read without storing credentials in source control

## Local environment setup

### 1. Create and activate the Conda environment

From the project root:

```powershell
conda activate data_health_monitor
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure Databricks authentication

This project expects the developer machine to already have Databricks OAuth configured through the Databricks CLI or another supported Databricks client auth flow.

```powershell
databricks auth login
```

databricks auth profiles

Then validate the active identity:

```powershell
databricks current-user me
```

The SDK call pattern used in the project follows the working notebook implementation:

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
```

## Run the backend

Open Terminal 1 in the project root and run:

```powershell
uvicorn data_health_monitor.main:app --reload
```

Backend URLs:

- http://127.0.0.1:8000/health
- http://127.0.0.1:8000/docs

## Application logging

Data Health Monitor emits structured JSON logs to stdout and a rotating local file.
Configure the log level, file location, rotation size, and retained archives with
these environment variables:

```env
APP_LOG_LEVEL=INFO
APP_LOG_FILE=logs/data_health_monitor.log
APP_LOG_MAX_BYTES=10485760
APP_LOG_BACKUP_COUNT=5
```

The default configuration retains the active log and five archives of up to 10 MiB
each. Local logs are written under `logs/`, which is excluded from source control.

## LLM configuration

LiteLLM is the application-facing LLM provider abstraction. Configure its provider and default model through environment variables; no credentials are stored in source control.

```env
LITELLM_MODEL=openai/gpt-4.1-mini
LITELLM_API_BASE=
LITELLM_API_KEY=
```

`LITELLM_MODEL` is the default model, while `LITELLM_API_BASE` and `LITELLM_API_KEY` support providers that require a custom API endpoint or key.

## Databricks Model Serving configuration

Databricks Model Serving invokes a configured model through the OpenAI-compatible Databricks AI Gateway and is intentionally separate from LiteLLM. It uses the existing Databricks unified authentication profile.

```env
DATABRICKS_PROFILE=DEFAULT
DATABRICKS_SERVING_MODEL=databricks-claude-haiku-4-5
```

`DATABRICKS_PROFILE` selects the configured Databricks authentication profile and `DATABRICKS_SERVING_MODEL` selects the AI Gateway model.

## Run the Streamlit frontend

Open Terminal 2 in the project root and run:

```powershell
streamlit run frontend/streamlit_app.py
```

Frontend URL:

- http://localhost:8501

## API endpoints

Streamlit uses `/api/v1`. The earlier `/api` contract remains active only for
temporary compatibility and is protected by an executable OpenAPI contract test.

V1 keeps stable resource IDs in URL paths. Catalog, schema, table, payor, file
type, and search filters are validated JSON request bodies on explicit `POST`
action endpoints. It does not use request bodies with `GET` operations.

- GET /health
- GET /api/v1/databricks/catalogs
- POST /api/v1/databricks/schemas:lookup
- POST /api/v1/databricks/schema-objects:lookup
- POST /api/v1/databricks/tables:lookup
- GET /api/v1/test-cases
- POST /api/v1/test-cases
- GET /api/v1/test-cases/{test_case_id}
- GET /api/v1/payor-config/payors
- POST /api/v1/payor-config/file-types:lookup
- POST /api/v1/payor-config:lookup
- POST /api/v1/payor-config:search
- POST /api/v1/qa/validation-sql:search
- POST /api/v1/qa/validation-sql/{validation_sql_id}:execute

The full contract, including metadata and Genie operations, is available at
http://127.0.0.1:8000/docs. `POST /api/llm/chat` and
`POST /api/model-serving/predict` are legacy-only and are not used by Streamlit.

## LLM configuration

LiteLLM is the application-facing provider abstraction. Configure the provider and default model through environment variables or `.env` without committing credentials:

```env
LITELLM_MODEL=openai/gpt-4.1-mini
LITELLM_API_BASE=
LITELLM_API_KEY=
```

`LITELLM_MODEL` is required before calling `POST /api/llm/chat`. A request may override this default model.

## Databricks Model Serving configuration

Databricks Model Serving invokes a configured model through the OpenAI-compatible Databricks AI Gateway. It uses the existing unified authentication profile; do not add a personal access token to the application.

```env
DATABRICKS_PROFILE=your-profile
DATABRICKS_SERVING_MODEL=databricks-claude-haiku-4-5
```

`LiteLLMService` and `DatabricksModelServingService` are intentionally separate. LiteLLM is a gateway to external providers, while Databricks Model Serving invokes a configured Databricks-hosted endpoint.

## Example response

```json
{
  "status": "healthy"
}
```

## Notes

- No Databricks secrets are stored in source files.
- No custom authentication logic is implemented.
- The app is intentionally simple and ready to extend later with more metadata intelligence.

