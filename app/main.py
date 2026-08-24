from fastapi import FastAPI

from app.api.routes import metadata_router, router

app = FastAPI(title="QA Automation API", version="0.1.0")
app.include_router(router)
app.include_router(metadata_router)


@app.get("/health")
def health_check():
    return {"status": "healthy"}
