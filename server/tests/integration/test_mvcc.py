"""MVCC / locking / isolation experiments — the physics, asserted.

Each test runs one lab scenario and asserts the Postgres behavior it
demonstrates, so the lab (and our understanding) is regression-proofed.
"""

import pytest

from experiments.mvcc_lab import (
    experiment_a_read_committed,
    experiment_b_repeatable_read,
    experiment_c_update_contention,
    experiment_d_select_for_update,
    experiment_e_blocking,
    experiment_f_deadlock,
    experiment_g_pool_exhaustion,
    lab_database,
)


@pytest.fixture
def mvcc_engine(admin_engine):
    """Scratch database dedicated to MVCC experiments."""
    with lab_database(admin_engine) as engine:
        yield engine


def test_a_read_committed_allows_non_repeatable_read(mvcc_engine):
    result = experiment_a_read_committed(mvcc_engine)

    assert result["first_read"] == 1000
    assert result["second_read"] == 1200  # saw B's commit mid-transaction


def test_b_repeatable_read_snapshot_stable_and_write_conflict(mvcc_engine):
    result = experiment_b_repeatable_read(mvcc_engine)

    assert result["first_read"] == 1000
    assert result["second_read"] == 1000  # snapshot frozen
    assert "could not serialize access" in result["write_error"]


def test_c_app_level_read_modify_write_loses_update(mvcc_engine):
    result = experiment_c_update_contention(mvcc_engine)

    assert result["a_read"] == 1000
    assert result["b_read"] == 1000  # both read the same base
    assert result["final_balance"] == 1100  # 100 lost — anomaly demonstrated


def test_d_select_for_update_serializes_updates(mvcc_engine):
    result = experiment_d_select_for_update(mvcc_engine)

    assert result["a_read"] == 1000
    assert result["b_read"] == 1100  # B waited, then read A's committed base
    assert result["final_balance"] == 1200  # both increments survived


def test_e_lock_wait_times_out(mvcc_engine):
    result = experiment_e_blocking(mvcc_engine)

    assert result["error_code"] == "55P03"  # lock_not_available
    assert result["waited_seconds"] >= 0.9  # honored lock_timeout ~1s


def test_f_deadlock_detected_one_victim(mvcc_engine):
    result = experiment_f_deadlock(mvcc_engine)

    assert result["victim_error_code"] == "40P01"  # deadlock_detected
    assert result["survivor_committed"] is True
    assert result["deadlock_detected_seconds"] >= 0.5  # deadlock_timeout ~1s


def test_g_pool_exhaustion_times_out(mvcc_engine):
    result = experiment_g_pool_exhaustion(mvcc_engine)

    assert result["timeout_error"] is True
    assert result["pool_status_before"] != result["pool_status_after"]
    assert result["waited_seconds"] >= 0.9  # pool_timeout ~1s
