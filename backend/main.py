"""Initial company API: stages 5-7 only."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from backend.core.config import get_settings
from backend.database.connection import build_engine, initialize_database, database_status

settings = get_settings()

@asynccontextmanager
async def lifespan(application: FastAPI):
    engine = build_engine(settings.database_url)
    try:
        initialize_database(engine)
        application.state.database_engine = engine
        yield
    finally:
        engine.dispose()

app = FastAPI(lifespan=lifespan, title=settings.app_name, version=settings.version,
              description="AI Autonomous Company initial API; AI employees not implemented")

@app.get("/")
def root() -> dict[str, str]:
    return {"project": settings.app_name, "status": "development", "docs": "/docs"}

@app.get("/health")
@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "component": "api",
            "environment": settings.environment, "version": settings.version}

@app.get("/api/v1/database/health")
def database_health(request: Request) -> dict[str, str]:
    engine = getattr(request.app.state, "database_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Database engine is not initialized")
    try:
        return database_status(engine)
    except (SQLAlchemyError, RuntimeError):
        raise HTTPException(status_code=503, detail="Database connection unavailable") from None
