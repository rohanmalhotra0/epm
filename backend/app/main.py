"""EPM Wizard backend — local FastAPI application.

Binds to the local machine / Docker network only. No hosted services.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import (
    routes_agent,
    routes_artifacts,
    routes_attachments,
    routes_context,
    routes_conversations,
    routes_diagnostics,
    routes_environments,
    routes_meta,
    routes_projects,
    routes_providers,
    routes_reports,
    routes_settings,
)
from .config import get_settings
from .db.init import initialize
from .logging import configure_logging, get_logger
from .services import backups

log = get_logger("epmwizard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    initialize(seed=True, migrate=settings.startup_migrations)
    if settings.is_sqlite:
        try:
            backups.create_backup()
        except OSError as exc:  # a failed backup must never block startup
            log.warning("startup_backup_failed", error=str(exc))
    else:
        log.info("startup_backup_skipped", reason="managed database — backups are the database service's job")
    log.info("startup", app=settings.app_name, version=settings.version, data_dir=str(settings.data_dir))
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (routes_meta, routes_projects, routes_conversations, routes_environments,
                   routes_providers, routes_context, routes_artifacts, routes_attachments,
                   routes_diagnostics, routes_reports, routes_settings, routes_agent):
        app.include_router(module.router)
    return app


app = create_app()
