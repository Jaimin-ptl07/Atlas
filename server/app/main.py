from fastapi import FastAPI

from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.debug
    )

    app.include_router(health_router)
    app.include_router(documents_router)
    app.include_router(jobs_router)

    if settings.experiments_enabled:
        from app.api.routes.experiment import router as experiment_router

        app.include_router(experiment_router)

    return app


app = create_app()