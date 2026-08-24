# QA Automation API

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
conda activate qa_auto
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
uvicorn app.main:app --reload
```

Backend URLs:

- http://127.0.0.1:8000/health
- http://127.0.0.1:8000/docs

## Run the Streamlit frontend

Open Terminal 2 in the project root and run:

```powershell
streamlit run frontend/streamlit_app.py
```

Frontend URL:

- http://localhost:8501

## API endpoints

- GET /health
- GET /api/databricks/catalogs
- GET /api/databricks/catalogs/{catalog_name}/schemas
- GET /api/databricks/catalogs/{catalog_name}/schemas/{schema_name}/objects
- GET /api/databricks/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}

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

