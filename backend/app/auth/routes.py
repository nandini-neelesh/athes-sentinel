from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.auth.schemas import LoginRequest, TokenResponse, UserResponse
from backend.app.auth.service import (
    authenticate_user,
    create_access_token,
    get_current_user,
)
from backend.app.database.session import get_db


router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db=Depends(get_db)):
    user = authenticate_user(body.username, body.password, db)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        {
            "sub": user.username,
            "role": user.role,
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
        },
    }


@router.get("/me", response_model=UserResponse)
def read_current_user(current_user=Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
    }
