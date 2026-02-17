from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import router
from ..core.database import engine
from ..models.schema import Base
from ..core.config import settings

app = FastAPI(title="Antigravity Prospector", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routes
app.include_router(router, prefix="/api/v1")

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        # Create Tables (for dev/demo convenience)
        await conn.run_sync(Base.metadata.create_all)

@app.get("/")
async def root():
    return {"status": "ok", "system": "Antigravity Prospector"}
