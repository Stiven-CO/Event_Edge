from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routers import analysis, assets, control, events
from backend.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Event Edge API",
        description="Estudio probabilístico de eventos Earnings & Gap para acciones americanas.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(control.router)
    app.include_router(assets.router)
    app.include_router(events.router)
    app.include_router(analysis.router)

    @app.get("/", tags=["root"])
    async def root():
        return {"service": "Event Edge", "version": "0.1.0", "docs": "/docs"}

    return app


app = create_app()
