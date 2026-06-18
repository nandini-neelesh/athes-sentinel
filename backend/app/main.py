import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.app.analytics.routes import router as analytics_router
from backend.app.auth.routes import router as auth_router
from backend.app.auth.service import create_demo_users
from backend.app.database import models  # Registers SQLAlchemy models.
from backend.app.database.session import Base, engine, SessionLocal
from backend.app.detection.routes import router as ml_router
from backend.app.features.routes import router as features_router
from backend.app.incidents.routes import router as incidents_router
from backend.app.logs.routes import router as logs_router


DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

allowed_origins_env = os.getenv("ATHES_ALLOWED_ORIGINS")

if allowed_origins_env:
    allowed_origins = [
        origin.strip()
        for origin in allowed_origins_env.split(",")
        if origin.strip()
    ]
else:
    allowed_origins = DEFAULT_ALLOWED_ORIGINS


app = FastAPI(
    title="Athes Sentinel API",
    description="API for the Athes Sentinel placement project.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analytics_router)
app.include_router(auth_router)
app.include_router(features_router)
app.include_router(incidents_router)
app.include_router(logs_router)
app.include_router(ml_router)


class TestLogRequest(BaseModel):
    ip_address: str
    endpoint: str
    status_code: int


@app.on_event("startup")
def create_database_tables():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        create_demo_users(db)
    finally:
        db.close()


@app.get("/")
def health_check():
    return {"message": "Athes Sentinel API is running"}


@app.post("/test-log")
def test_log(body: TestLogRequest):
    return {
        "message": "Log received",
        "data": {
            "ip_address": body.ip_address,
            "endpoint": body.endpoint,
            "status_code": body.status_code,
        },
    }
