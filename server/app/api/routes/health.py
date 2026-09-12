from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(
    prefix="",
    tags=["Health"],
)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", desc="All systems operational")

@router.get("/ready", response_model=HealthResponse)
async def ready() -> HealthResponse:
    return HealthResponse(status="ready", desc="Service is ready")