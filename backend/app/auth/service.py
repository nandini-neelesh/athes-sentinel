import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.app.database.models import User
from backend.app.database.session import get_db


logger = logging.getLogger(__name__)

DEFAULT_SECRET_KEY = "athes-dev-secret-change-before-production"

configured_secret_key = os.getenv("ATHES_SECRET_KEY")

if configured_secret_key is not None:
    configured_secret_key = configured_secret_key.strip()

if os.getenv("ATHES_ENV") == "production" and not configured_secret_key:
    raise RuntimeError(
        "ATHES_SECRET_KEY must be configured when ATHES_ENV is production."
    )

SECRET_KEY = configured_secret_key or DEFAULT_SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480


password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password):
    return password_context.hash(password)


def verify_password(plain_password, hashed_password):
    return password_context.verify(plain_password, hashed_password)


def get_user_by_username(username, db):
    return db.query(User).filter(User.username == username).first()


def authenticate_user(username, password, db):
    user = get_user_by_username(username, db)

    if user is None:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user


def create_access_token(data, expires_delta=None):
    token_data = data.copy()

    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    expires_at = datetime.now(timezone.utc) + expires_delta
    token_data.update({"exp": expires_at})

    return jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise credentials_exception from exc


def get_current_user(token=Depends(oauth2_scheme), db=Depends(get_db)):
    payload = decode_access_token(token)
    username = payload.get("sub")

    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_username(username, db)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_role(allowed_roles):
    def role_dependency(current_user=Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )

        return current_user

    return role_dependency


DEMO_USERS = (
    ("admin", "admin123", "admin"),
    ("analyst", "analyst123", "analyst"),
)

MIN_PASSWORD_LENGTH = 8


def is_production():
    return os.getenv("ATHES_ENV", "").strip().lower() == "production"


def demo_users_enabled():
    """Demo accounts are a development convenience, never a production default."""
    flag = os.getenv("ATHES_SEED_DEMO_USERS", "").strip().lower()

    if flag in {"1", "true", "yes"}:
        return True

    if flag in {"0", "false", "no"}:
        return False

    return not is_production()


def create_demo_users(db):
    """Create the well-known demo accounts (development and tests only)."""
    for username, password, role in DEMO_USERS:
        if get_user_by_username(username, db) is None:
            db.add(
                User(
                    username=username,
                    hashed_password=hash_password(password),
                    role=role,
                )
            )

    db.commit()


def upsert_configured_user(db, username, password, role):
    """Create a user, or reset the password of an existing one."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise RuntimeError(
            f"Password for configured {role} '{username}' must be at least "
            f"{MIN_PASSWORD_LENGTH} characters."
        )

    user = get_user_by_username(username, db)

    if user is None:
        db.add(
            User(
                username=username,
                hashed_password=hash_password(password),
                role=role,
            )
        )
    elif not verify_password(password, user.hashed_password) or user.role != role:
        user.hashed_password = hash_password(password)
        user.role = role


def remove_default_demo_users(db):
    """Delete demo accounts that still use their publicly known password."""
    removed = []

    for username, password, _role in DEMO_USERS:
        user = get_user_by_username(username, db)

        if user is not None and verify_password(password, user.hashed_password):
            db.delete(user)
            removed.append(username)

    return removed


def seed_users(db):
    """Provision login accounts for the current environment.

    * ATHES_ADMIN_USERNAME / ATHES_ADMIN_PASSWORD and
      ATHES_ANALYST_USERNAME / ATHES_ANALYST_PASSWORD create (or update) real
      accounts from environment variables, so no credential lives in the code.
    * The public demo accounts are only created outside production, or when
      ATHES_SEED_DEMO_USERS=true is set explicitly.
    * In production without that flag, any leftover demo account that still has
      its default password is removed.
    """
    configured = (
        ("ATHES_ADMIN_USERNAME", "ATHES_ADMIN_PASSWORD", "admin"),
        ("ATHES_ANALYST_USERNAME", "ATHES_ANALYST_PASSWORD", "analyst"),
    )

    for username_var, password_var, role in configured:
        username = os.getenv(username_var, "").strip()
        password = os.getenv(password_var, "")

        if username and password:
            upsert_configured_user(db, username, password, role)
        elif username or password:
            raise RuntimeError(
                f"{username_var} and {password_var} must be set together."
            )

    db.flush()

    if demo_users_enabled():
        create_demo_users(db)
    else:
        removed = remove_default_demo_users(db)

        if removed:
            logger.warning(
                "Removed default demo accounts from the database: %s",
                ", ".join(removed),
            )

    db.commit()

    if is_production() and db.query(User).count() == 0:
        logger.warning(
            "No login accounts exist. Set ATHES_ADMIN_USERNAME and "
            "ATHES_ADMIN_PASSWORD so someone can sign in."
        )
