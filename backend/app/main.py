from fastapi import FastAPI
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


app = FastAPI(
    title="Athes Sentinel API",
    description="API for the Athes Sentinel placement project.",
    version="1.0.0",
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
