import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.app.database.models import User
from backend.app.database.session import get_db


SECRET_KEY = os.getenv(
    "ATHES_SECRET_KEY",
    "athes-dev-secret-change-before-production",
)
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


def create_demo_users(db):
    admin_user = get_user_by_username("admin", db)
    analyst_user = get_user_by_username("analyst", db)

    if admin_user is None:
        db.add(
            User(
                username="admin",
                hashed_password=hash_password("admin123"),
                role="admin",
            )
        )

    if analyst_user is None:
        db.add(
            User(
                username="analyst",
                hashed_password=hash_password("analyst123"),
                role="analyst",
            )
        )

    db.commit()
