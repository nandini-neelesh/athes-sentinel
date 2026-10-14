import logging
import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.analytics.routes import router as analytics_router
from backend.app.auth.routes import router as auth_router
from backend.app.auth.service import seed_users
from backend.app.database import models  # Registers SQLAlchemy models.
from backend.app.database.session import Base, engine, SessionLocal
from backend.app.detection.routes import router as ml_router
from backend.app.features.routes import router as features_router
from backend.app.incidents.routes import router as incidents_router
from backend.app.logs.routes import router as logs_router
from backend.app.network.routes import router as network_router


logger = logging.getLogger("athes.startup")

DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:5173",
]

allowed_origins_env = os.getenv("ATHES_ALLOWED_ORIGINS", "").strip()
application_environment = os.getenv("ATHES_ENV", "").strip().lower()

if allowed_origins_env:
    # A trailing slash ("https://app.vercel.app/") never matches the browser's
    # Origin header, so strip it instead of failing every CORS preflight.
    allowed_origins = [
        origin.strip().rstrip("/")
        for origin in allowed_origins_env.split(",")
        if origin.strip()
    ]
elif application_environment == "production":
    raise RuntimeError(
        "ATHES_ALLOWED_ORIGINS must be configured when ATHES_ENV is production."
    )
else:
    allowed_origins = DEFAULT_ALLOWED_ORIGINS


app = FastAPI(
    title="Athes Sentinel API",
    description="API for the Athes Sentinel placement project.",
    version="1.0.0",
)

# Optional: let Vercel preview deployments call the API, e.g.
# ATHES_ALLOWED_ORIGIN_REGEX=https://athes-sentinel-.*\.vercel\.app
allowed_origin_regex = os.getenv("ATHES_ALLOWED_ORIGIN_REGEX", "").strip() or None

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allowed_origin_regex,
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
app.include_router(network_router)


DB_CONNECT_ATTEMPTS = int(os.getenv("ATHES_DB_CONNECT_ATTEMPTS", "5"))
DB_CONNECT_DELAY_SECONDS = float(os.getenv("ATHES_DB_CONNECT_DELAY", "4"))


def initialise_database():
    """Create tables and seed users, retrying while the database wakes up.

    Hosted Postgres instances (Render, Neon, Supabase) can take several seconds
    to accept connections after idling. If the database is genuinely
    unreachable the error is logged with an actionable hint and re-raised, so
    the failure is obvious in the logs rather than a bare "exited with status 3".
    Configuration mistakes (RuntimeError) are raised immediately without retrying.
    """
    last_error = None

    for attempt in range(1, DB_CONNECT_ATTEMPTS + 1):
        try:
            Base.metadata.create_all(bind=engine)

            db = SessionLocal()

            try:
                seed_users(db)
            finally:
                db.close()

            return
        except SQLAlchemyError as exc:
            last_error = exc
            logger.warning(
                "Database initialisation failed (attempt %s/%s): %s",
                attempt,
                DB_CONNECT_ATTEMPTS,
                exc.__class__.__name__,
            )

            if attempt < DB_CONNECT_ATTEMPTS:
                time.sleep(DB_CONNECT_DELAY_SECONDS)

    logger.error(
        "Could not initialise the database after %s attempts. Check that "
        "DATABASE_URL points to a database that still exists (free Render "
        "Postgres instances expire after 30 days) and that its credentials "
        "are correct.",
        DB_CONNECT_ATTEMPTS,
    )
    raise last_error


@app.on_event("startup")
def create_database_tables():
    initialise_database()


@app.get("/")
def health_check():
    return {"message": "Athes Sentinel API is running"}


@app.get("/health")
def database_health_check():
    """Deeper check that also verifies the database connection."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "unreachable"},
        )

    return {"status": "ok", "database": "connected"}
