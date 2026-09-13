"""Experiment-only routes: instrumented read + metrics snapshot/reset.

Mounted by create_app() only when ATLAS_EXPERIMENTS_ENABLED=true, so the
production API surface stays untouched.
"""

from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db, get_engine
from app.experiments.metrics import experiment_metrics
from app.schemas.document import DocumentResponse
from app.services.document import DocumentService

router = APIRouter(prefix="/experiment", tags=["Experiments"])


@router.get("/read/{document_id}", response_model=DocumentResponse)
def experiment_read(document_id: int, session: Annotated[Session, Depends(get_db)]) -> DocumentResponse:
    """One read, fully timed: request total vs connection acquisition vs query.

    session.connection() forces the pool checkout NOW, so acquisition time
    is measured separately instead of being buried in the first execute().
    """
    metrics = experiment_metrics
    metrics.request_started()
    started = perf_counter()
    try:
        acq_start = perf_counter()
        session.connection()
        acquisition = perf_counter() - acq_start

        document = DocumentService(session).get_document(document_id)

        metrics.observe_acquisition(acquisition)
        metrics.observe_request(perf_counter() - started, ok=True)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )
        return DocumentResponse.model_validate(document)
    except HTTPException:
        raise  # a 404 is still a completed (ok) request
    except Exception:
        metrics.observe_request(perf_counter() - started, ok=False)
        raise
    finally:
        metrics.request_finished()


@router.get("/metrics")
def experiment_metrics_snapshot(session: Annotated[Session, Depends(get_db)]) -> dict:
    snapshot = experiment_metrics.snapshot()
    snapshot["pool"]["size"] = get_engine().pool.size()
    snapshot["pool"]["max_overflow"] = get_engine().pool._max_overflow
    # Server-side truth: connections from ALL clients of this database
    # (includes this very query's own connection — checked out right now).
    snapshot["postgres_connections"] = session.execute(
        text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
    ).scalar_one()
    return snapshot


@router.post("/reset")
def reset_experiment_metrics() -> dict:
    experiment_metrics.reset()
    return {"status": "reset"}
