from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class UserRead(BaseModel):
    id: str
    email: str
    full_name: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate) -> UserRead:
    """Register a new user account."""
    # TODO: hash password with passlib, persist to DB
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.post("/token", response_model=Token)
async def login(form: OAuth2PasswordRequestForm = Depends()) -> Token:
    """Exchange credentials for JWT access + refresh token pair."""
    # TODO: verify credentials against DB, issue JWT
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.post("/refresh", response_model=Token)
async def refresh_token(refresh_token: str) -> Token:
    """Exchange a valid refresh token for a new access token."""
    # TODO: validate refresh token signature and expiry
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.get("/me", response_model=UserRead)
async def me(token: str = Depends(oauth2_scheme)) -> UserRead:
    """Return the currently authenticated user."""
    # TODO: decode JWT, look up user in DB
    raise HTTPException(status_code=501, detail="Not implemented yet")
