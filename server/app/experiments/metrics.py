"""In-memory metrics registry for database experiments (dev only).

Thread-safe: sync endpoints run in FastAPI's threadpool, so gauges and
lists are guarded by a lock. Deliberately dependency-free — no metrics
platform, just numbers we can reason about.
"""

import threading
from time import perf_counter


def _percentile(sorted_values: list[float], fraction: float) -> float:
    """Nearest-rank percentile of an already-sorted list (0-100 scale input as fraction)."""
    if not sorted_values:
        return 0.0
    rank = min(len(sorted_values) - 1, round(fraction * (len(sorted_values) - 1)))
    return sorted_values[rank]


def _summary(values: list[float]) -> dict:
    ordered = sorted(values)
    count = len(ordered)
    avg = sum(ordered) / count if count else 0.0
    return {
        "count": count,
        "avg": round(avg, 6),
        "p50": round(_percentile(ordered, 0.50), 6),
        "p95": round(_percentile(ordered, 0.95), 6),
        "p99": round(_percentile(ordered, 0.99), 6),
    }


def _ms(seconds: float) -> float:
    return seconds * 1000.0


class ExperimentMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reset_unlocked()

    # ---- recording -------------------------------------------------------

    def reset(self) -> None:
        with self._lock:
            self._reset_unlocked()

    def _reset_unlocked(self) -> None:
        self._request_count = 0
        self._request_errors = 0
        self._in_flight = 0
        self._max_in_flight = 0
        self._latencies: list[float] = []
        self._query_times: list[float] = []
        self._acquisition_times: list[float] = []
        self._pool_checkouts = 0
        self._pool_checked_out = 0
        self._pool_max_checked_out = 0
        self._pool_connections_created = 0

    def request_started(self) -> None:
        with self._lock:
            self._in_flight += 1
            self._max_in_flight = max(self._max_in_flight, self._in_flight)

    def request_finished(self) -> None:
        with self._lock:
            self._in_flight -= 1

    def observe_request(self, latency_seconds: float, *, ok: bool) -> None:
        with self._lock:
            self._request_count += 1
            if not ok:
                self._request_errors += 1
            self._latencies.append(latency_seconds)

    def observe_query_time(self, seconds: float) -> None:
        with self._lock:
            self._query_times.append(seconds)

    def observe_acquisition(self, seconds: float) -> None:
        with self._lock:
            self._acquisition_times.append(seconds)

    def record_checkout(self) -> None:
        with self._lock:
            self._pool_checkouts += 1
            self._pool_checked_out += 1
            self._pool_max_checked_out = max(
                self._pool_max_checked_out, self._pool_checked_out
            )

    def record_checkin(self) -> None:
        with self._lock:
            self._pool_checked_out -= 1

    def record_connection_created(self) -> None:
        with self._lock:
            self._pool_connections_created += 1

    # ---- reporting -------------------------------------------------------

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "requests": {
                    "count": self._request_count,
                    "errors": self._request_errors,
                    "in_flight": self._in_flight,
                    "max_in_flight": self._max_in_flight,
                    "latency_ms": _summary([_ms(v) for v in self._latencies]),
                },
                "pool": {
                    "checkouts": self._pool_checkouts,
                    "checked_out": self._pool_checked_out,
                    "max_checked_out": self._pool_max_checked_out,
                    "connections_created": self._pool_connections_created,
                },
                "timings": {
                    "acquisition_ms": _summary([_ms(v) for v in self._acquisition_times]),
                    "query_ms": _summary([_ms(v) for v in self._query_times]),
                },
            }


experiment_metrics = ExperimentMetrics()


def attach_instrumentation(engine, metrics: ExperimentMetrics) -> None:
    """Hook pool + cursor events of an Engine onto a metrics registry."""
    from sqlalchemy import event

    @event.listens_for(engine.pool, "connect")
    def _on_connect(dbapi_connection, connection_record):
        # A NEW physical database connection was opened (TCP + auth cost paid)
        metrics.record_connection_created()

    @event.listens_for(engine.pool, "checkout")
    def _on_checkout(dbapi_connection, connection_record, connection_proxy):
        metrics.record_checkout()

    @event.listens_for(engine.pool, "checkin")
    def _on_checkin(dbapi_connection, connection_record):
        metrics.record_checkin()

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor(conn, cursor, statement, parameters, context, executemany):
        context._experiment_query_start = perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor(conn, cursor, statement, parameters, context, executemany):
        start = getattr(context, "_experiment_query_start", None)
        if start is not None:
            metrics.observe_query_time(perf_counter() - start)
