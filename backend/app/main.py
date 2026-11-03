from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import text

from app.auth import protected_router, router as auth_router
from app.config import settings
from app.db import SessionLocal



@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
    yield
    application.state.redis.close()


app = FastAPI(title="Chubby AI Platform API", version="0.1.0", description="Tenant-aware foundation for Chubby Group restaurant operations.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "X-CSRF-Token"], expose_headers=["X-CSRF-Token"])
app.include_router(auth_router)
app.include_router(protected_router)


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health():
    return {"status": "ok"}


@app.get("/ready", response_model=HealthResponse, tags=["system"])
def ready():
    with SessionLocal() as session:
        role = session.execute(text("SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
        if role[0] != "chubby_app" or role[1] or role[2]:
            raise HTTPException(status_code=503, detail="Application database role is not restricted")
    app.state.redis.ping()
    return {"status": "ready"}
