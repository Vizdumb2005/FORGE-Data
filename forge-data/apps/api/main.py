import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import auth, connectors, health, llm, workbooks


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialise connection pools, etc.
    yield
    # Shutdown: clean up resources


app = FastAPI(
    title="FORGE Data API",
    description="Self-hosted data intelligence platform backend",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router, tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(connectors.router, prefix="/connectors", tags=["connectors"])
app.include_router(workbooks.router, prefix="/workbooks", tags=["workbooks"])
app.include_router(llm.router, prefix="/llm", tags=["llm"])
