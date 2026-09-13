"""Unit tests for the experiment metrics registry (no database needed)."""


def _registry():
    from app.experiments.metrics import ExperimentMetrics

    return ExperimentMetrics()


def test_latency_percentiles():
    metrics = _registry()
    for ms in (10, 20, 30, 40, 50):
        metrics.observe_request(ms / 1000, ok=True)

    snapshot = metrics.snapshot()

    assert snapshot["requests"]["count"] == 5
    assert snapshot["requests"]["latency_ms"]["p50"] == 30.0
    assert snapshot["requests"]["latency_ms"]["p95"] == 50.0


def test_request_gauge_tracks_concurrency():
    metrics = _registry()
    metrics.request_started()
    metrics.request_started()
    metrics.request_started()

    assert metrics.snapshot()["requests"]["in_flight"] == 3
    assert metrics.snapshot()["requests"]["max_in_flight"] == 3

    metrics.request_finished()
    assert metrics.snapshot()["requests"]["in_flight"] == 2
    assert metrics.snapshot()["requests"]["max_in_flight"] == 3


def test_pool_gauge_tracks_checkout_checkin():
    metrics = _registry()
    metrics.record_checkout()
    metrics.record_checkout()
    metrics.record_checkin()

    snapshot = metrics.snapshot()

    assert snapshot["pool"]["checked_out"] == 1
    assert snapshot["pool"]["max_checked_out"] == 2
    assert snapshot["pool"]["checkouts"] == 2


def test_query_and_acquisition_timings_recorded():
    metrics = _registry()
    metrics.observe_query_time(0.002)
    metrics.observe_acquisition(0.001)

    snapshot = metrics.snapshot()

    assert snapshot["timings"]["query_ms"]["avg"] == 2.0
    assert snapshot["timings"]["acquisition_ms"]["avg"] == 1.0


def test_errors_counted_separately():
    metrics = _registry()
    metrics.observe_request(0.01, ok=True)
    metrics.observe_request(0.02, ok=False)

    snapshot = metrics.snapshot()

    assert snapshot["requests"]["count"] == 2
    assert snapshot["requests"]["errors"] == 1


def test_reset_clears_everything():
    metrics = _registry()
    metrics.request_started()
    metrics.observe_request(0.01, ok=True)
    metrics.record_checkout()
    metrics.observe_query_time(0.001)

    metrics.reset()
    snapshot = metrics.snapshot()

    assert snapshot["requests"]["count"] == 0
    assert snapshot["requests"]["in_flight"] == 0
    assert snapshot["pool"]["checked_out"] == 0
    assert snapshot["timings"]["query_ms"]["count"] == 0
