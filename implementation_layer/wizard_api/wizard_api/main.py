from fastapi import FastAPI

from wizard_api.routers.sessions import router as sessions_router

app = FastAPI(title="GAIK Wizard API", version="0.1.0")

app.include_router(sessions_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
