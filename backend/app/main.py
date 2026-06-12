from fastapi import FastAPI
from pydantic import BaseModel

from backend.app.database import models  # Registers SQLAlchemy models.
from backend.app.database.session import Base, engine
from backend.app.logs.routes import router as logs_router


app = FastAPI(
    title="Athes Sentinel API",
    description="API for the Athes Sentinel placement project.",
    version="1.0.0",
)

app.include_router(logs_router)


class TestLogRequest(BaseModel):
    ip_address: str
    endpoint: str
    status_code: int


@app.on_event("startup")
def create_database_tables():
    Base.metadata.create_all(bind=engine)


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
