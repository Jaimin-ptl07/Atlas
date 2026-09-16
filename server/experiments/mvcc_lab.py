"""MVCC, isolation, locking, deadlock and pool experiments (A-G).

Session-level experiments against a scratch database — no HTTP, no load
generator, no timing races in the harness itself. Each experiment runs a
controlled interleaving of transactions and returns structured results.

Usage:
    uv run python -m experiments.mvcc_lab --exp all
    uv run python -m experiments.mvcc_lab --exp B
"""

import argparse
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

LAB_DB = "atlas_mvcc_lab"


# --------------------------------------------------------------------------
# Scratch database lifecycle
# --------------------------------------------------------------------------


@contextmanager
def lab_database(admin_engine: Engine) -> Iterator[Engine]:
    """Dedicated scratch database with a classic accounts table."""
    base_url = admin_engine.url.render_as_string(hide_password=False).rsplit("/", 1)[0]
    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{LAB_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{LAB_DB}"'))

    engine = create_engine(f"{base_url}/{LAB_DB}")
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE accounts (id int PRIMARY KEY, balance int NOT NULL)")
        )
        conn.execute(
            text("INSERT INTO accounts (id, balance) VALUES (1, 1000), (2, 1000)")
        )
    try:
        yield engine
    finally:
        engine.dispose()
        with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{LAB_DB}" WITH (FORCE)'))


def _reset(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE accounts SET balance = 1000"))


def _read(conn: Connection, account_id: int = 1) -> int:
    return conn.execute(
        text("SELECT balance FROM accounts WHERE id = :id"), {"id": account_id}
    ).scalar_one()


def _sqlstate(error: SQLAlchemyError) -> str:
    orig = getattr(error, "orig", None)
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", "") or ""


# --------------------------------------------------------------------------
# Experiment A — READ COMMITTED: non-repeatable read
# --------------------------------------------------------------------------


def experiment_a_read_committed(engine: Engine) -> dict:
    """Postgres default: every statement takes a fresh snapshot."""
    _reset(engine)
    log = []

    a = engine.connect()
    ta = a.begin()
    first = _read(a)
    log.append(f"[A] BEGIN (READ COMMITTED); SELECT balance -> {first}")

    b = engine.connect()
    with b.begin():
        b.execute(text("UPDATE accounts SET balance = 1200 WHERE id = 1"))
    log.append("[B] BEGIN; UPDATE balance=1200; COMMIT")

    second = _read(a)
    log.append(f"[A] SELECT balance again -> {second}   <-- saw B's commit mid-transaction!")
    ta.rollback()
    a.close()
    b.close()

    return {
        "log": log,
        "first_read": first,
        "second_read": second,
        "conclusion": "READ COMMITTED snapshots per statement: non-repeatable reads allowed.",
    }


# --------------------------------------------------------------------------
# Experiment B — REPEATABLE READ: snapshot isolation + write conflict
# --------------------------------------------------------------------------


def experiment_b_repeatable_read(engine: Engine) -> dict:
    _reset(engine)
    log = []

    a = engine.connect().execution_options(isolation_level="REPEATABLE READ")
    ta = a.begin()
    first = _read(a)
    log.append(f"[A] BEGIN ISOLATION LEVEL REPEATABLE READ; SELECT -> {first}")

    b = engine.connect()
    with b.begin():
        b.execute(text("UPDATE accounts SET balance = 1500 WHERE id = 1"))
    log.append("[B] UPDATE balance=1500; COMMIT")

    second = _read(a)
    log.append(f"[A] SELECT again -> {second}   <-- snapshot frozen, B's write invisible")

    write_error = ""
    error_code = ""
    try:
        a.execute(text("UPDATE accounts SET balance = balance + 1 WHERE id = 1"))
        ta.commit()
    except SQLAlchemyError as exc:
        write_error = str(getattr(exc, "orig", exc))
        error_code = _sqlstate(exc)
        ta.rollback()
    log.append(f"[A] UPDATE the changed row -> {error_code} serialization failure")
    a.close()
    b.close()

    return {
        "log": log,
        "first_read": first,
        "second_read": second,
        "write_error": write_error,
        "error_code": error_code,
        "conclusion": "REPEATABLE READ freezes a snapshot; concurrent writes to the same "
        "row are refused with 40001 (write-snapshot conflict).",
    }


# --------------------------------------------------------------------------
# Experiment C — row UPDATE contention: application-level lost update
# --------------------------------------------------------------------------


def experiment_c_update_contention(engine: Engine) -> dict:
    """Both sessions read 1000, compute in Python, write absolutes: one dies."""
    _reset(engine)
    log = []

    a = engine.connect()
    with a.begin():
        a_read = _read(a)
    log.append(f"[A] SELECT -> {a_read} (plain read, no lock, txn closed)")

    b = engine.connect()
    with b.begin():
        b_read = _read(b)
    log.append(f"[B] SELECT -> {b_read} (same base!)")

    with a.begin():
        a.execute(text("UPDATE accounts SET balance = :v WHERE id = 1"), {"v": a_read + 100})
    log.append(f"[A] UPDATE balance = {a_read}+100 = {a_read + 100}; COMMIT")

    with b.begin():
        b.execute(text("UPDATE accounts SET balance = :v WHERE id = 1"), {"v": b_read + 100})
    log.append(f"[B] UPDATE balance = {b_read}+100 = {b_read + 100}; COMMIT  <-- overwrites A")

    with engine.connect() as conn:
        final = _read(conn)
    a.close()
    b.close()
    log.append(f"     final balance -> {final}  (expected 1200; 100 was LOST)")

    return {
        "log": log,
        "a_read": a_read,
        "b_read": b_read,
        "final_balance": final,
        "conclusion": "Plain SELECT + application-side read-modify-write loses updates at "
        "any isolation level: reads don't lock, and the second write overwrites the first.",
    }


# --------------------------------------------------------------------------
# Experiment D — SELECT ... FOR UPDATE: pessimistic serialization
# --------------------------------------------------------------------------


def experiment_d_select_for_update(engine: Engine) -> dict:
    """Same scenario as C, but readers lock: B waits and sees A's result."""
    _reset(engine)
    log = []
    outcome: dict = {}

    a = engine.connect()
    ta = a.begin()
    a_read = a.execute(
        text("SELECT balance FROM accounts WHERE id = 1 FOR UPDATE")
    ).scalar_one()
    log.append(f"[A] BEGIN; SELECT ... FOR UPDATE -> {a_read} (row locked)")

    def b_thread() -> None:
        b = engine.connect()
        try:
            with b.begin():
                b_read = b.execute(
                    text("SELECT balance FROM accounts WHERE id = 1 FOR UPDATE")
                ).scalar_one()  # blocks until A commits
                outcome["b_read"] = b_read
                b.execute(
                    text("UPDATE accounts SET balance = :v WHERE id = 1"),
                    {"v": b_read + 100},
                )
        except SQLAlchemyError as exc:  # pragma: no cover - unexpected
            outcome["error"] = str(exc)

    thread = threading.Thread(target=b_thread)
    thread.start()
    time.sleep(0.3)  # let B arrive at the lock wait
    log.append("[B] SELECT ... FOR UPDATE -> BLOCKED (waiting for A)")

    a.execute(text("UPDATE accounts SET balance = :v WHERE id = 1"), {"v": a_read + 100})
    ta.commit()
    log.append(f"[A] UPDATE {a_read}+100; COMMIT (releases the lock)")
    thread.join()
    log.append(f"[B] ...unblocked, reads {outcome.get('b_read')} as base, +100, COMMIT")

    with engine.connect() as conn:
        final = _read(conn)
    a.close()
    log.append(f"     final balance -> {final}  (both increments survived)")

    return {
        "log": log,
        "a_read": a_read,
        "b_read": outcome.get("b_read"),
        "final_balance": final,
        "conclusion": "FOR UPDATE makes the read lock: B waits, then builds on A's committed "
        "value — application-level increments become safe.",
    }


# --------------------------------------------------------------------------
# Experiment E — blocking + lock_timeout
# --------------------------------------------------------------------------


def experiment_e_blocking(engine: Engine) -> dict:
    """An open transaction holds a row lock; the second writer waits, then
    fails cleanly once lock_timeout expires instead of hanging forever."""
    _reset(engine)
    log = []

    a = engine.connect()
    ta = a.begin()
    a.execute(text("UPDATE accounts SET balance = balance WHERE id = 1"))  # takes the lock
    log.append("[A] BEGIN; UPDATE row 1 (lock held, txn stays open)")

    b = engine.connect()
    tb = b.begin()
    b.execute(text("SET LOCAL lock_timeout = '1s'"))
    log.append("[B] BEGIN; SET LOCAL lock_timeout = 1s; UPDATE row 1 ... waiting")

    started = time.perf_counter()
    error_code, error_text = "", ""
    try:
        b.execute(text("UPDATE accounts SET balance = 2000 WHERE id = 1"))
        tb.commit()
    except SQLAlchemyError as exc:
        waited = time.perf_counter() - started
        tb.rollback()
        error_code = _sqlstate(exc)
        error_text = str(getattr(exc, "orig", exc))
        log.append(f"[B] -> {error_code} after {waited:.2f}s: lock timeout (fails, does not hang)")
    else:  # pragma: no cover - the timeout must fire
        waited = time.perf_counter() - started
        log.append(f"[B] unexpectedly acquired the lock after {waited:.2f}s")

    ta.rollback()
    a.close()
    b.close()

    return {
        "log": log,
        "error_code": error_code,
        "error_text": error_text,
        "waited_seconds": round(waited, 3),
        "conclusion": "Lock waits are real blocking: without lock_timeout the second writer "
        "hangs until the first session ends. SET lock_timeout converts a hang into an error.",
    }


# --------------------------------------------------------------------------
# Experiment F — deadlock: cycle detection
# --------------------------------------------------------------------------


def experiment_f_deadlock(engine: Engine) -> dict:
    """A locks 1 then wants 2; B locks 2 then wants 1. Postgres detects the
    cycle (deadlock_timeout, 1s default) and aborts exactly one victim."""
    _reset(engine)
    log = []
    barrier = threading.Barrier(2)
    outcome: dict = {"a": {}, "b": {}}

    def worker(name: str, first_row: int, second_row: int) -> None:
        conn = engine.connect()
        try:
            with conn.begin():
                conn.execute(
                    text("UPDATE accounts SET balance = balance WHERE id = :r"),
                    {"r": first_row},
                )
                barrier.wait(timeout=10)
                time.sleep(0.1)
                conn.execute(
                    text("UPDATE accounts SET balance = balance WHERE id = :r"),
                    {"r": second_row},
                )
            outcome[name]["committed"] = True
        except SQLAlchemyError as exc:
            outcome[name]["error_code"] = _sqlstate(exc)
            outcome[name]["error"] = str(getattr(exc, "orig", exc))
        finally:
            conn.close()

    started = time.perf_counter()
    ta = threading.Thread(target=worker, args=("a", 1, 2))
    tb = threading.Thread(target=worker, args=("b", 2, 1))
    ta.start()
    tb.start()
    ta.join(timeout=30)
    tb.join(timeout=30)
    detected = time.perf_counter() - started

    victim = "a" if "error_code" in outcome["a"] else "b"
    survivor = "b" if victim == "a" else "a"
    log.append("[A] locks row 1, then requests row 2  /  [B] locks row 2, then requests row 1")
    log.append(f"     cycle detected after {detected:.2f}s (deadlock_timeout = 1s)")
    log.append(f"     victim: session {victim.upper()} -> {outcome[victim].get('error_code')}")
    log.append(f"     survivor: session {survivor.upper()} committed = {outcome[survivor].get('committed')}")

    return {
        "log": log,
        "victim": victim,
        "victim_error_code": outcome[victim].get("error_code", ""),
        "victim_error": outcome[victim].get("error", ""),
        "survivor_committed": bool(outcome[survivor].get("committed")),
        "deadlock_detected_seconds": round(detected, 3),
        "conclusion": "Deadlocks are detected, not prevented: Postgres kills one transaction "
        "(40P01) so the other can proceed. Applications must retry the victim.",
    }


# --------------------------------------------------------------------------
# Experiment G — connection pool exhaustion
# --------------------------------------------------------------------------


def experiment_g_pool_exhaustion(engine: Engine) -> dict:
    """pool_size=1, overflow=0: the second checkout waits pool_timeout then
    raises — the same queue every request sits in when the pool is full."""
    url = engine.url.render_as_string(hide_password=False)
    tiny = create_engine(url, pool_size=1, max_overflow=0, pool_timeout=1)

    log = []
    c1 = tiny.connect()  # the only connection, checked out
    before = tiny.pool.status()
    log.append(f"[1] checked out the only connection   pool: {before}")

    from sqlalchemy.exc import TimeoutError as PoolTimeout

    timeout_error = False
    waited = 0.0
    started = time.perf_counter()
    try:
        tiny.connect()
    except PoolTimeout:
        waited = time.perf_counter() - started
        timeout_error = True
        log.append(f"[2] second checkout -> TimeoutError after {waited:.2f}s (pool_timeout=1s)")
    finally:
        c1.close()
        after = tiny.pool.status()
        tiny.dispose()

    log.append(f"[1] connection returned   pool: {after}")

    return {
        "log": log,
        "timeout_error": timeout_error,
        "pool_status_before": before,
        "pool_status_after": after,
        "waited_seconds": round(waited, 3),
        "conclusion": "A full pool queues checkouts for pool_timeout (30s default) and then "
        "raises — this is the 500-error path under saturation we saw in the QPS runs.",
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

EXPERIMENTS = {
    "A": ("READ COMMITTED — non-repeatable read", experiment_a_read_committed),
    "B": ("REPEATABLE READ — snapshot + write conflict", experiment_b_repeatable_read),
    "C": ("row UPDATE contention — lost update", experiment_c_update_contention),
    "D": ("SELECT ... FOR UPDATE — serialized RMW", experiment_d_select_for_update),
    "E": ("blocking + lock_timeout", experiment_e_blocking),
    "F": ("deadlock detection", experiment_f_deadlock),
    "G": ("connection pool exhaustion", experiment_g_pool_exhaustion),
}


def run(engine: Engine, keys: list[str]) -> None:
    for key in keys:
        title, func = EXPERIMENTS[key]
        result = func(engine)
        print()
        print("=" * 74)
        print(f"  Experiment {key}: {title}")
        print("=" * 74)
        for line in result["log"]:
            print(f"  {line}")
        print("-" * 74)
        print(f"  CONCLUSION: {result['conclusion']}")
        print("=" * 74)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exp", default="all", help="A B C D E F G or all")
    args = parser.parse_args()

    keys = list(EXPERIMENTS) if args.exp == "all" else [k.upper() for k in args.exp.split(",")]

    from app.db.session import get_engine

    admin = get_engine()
    with lab_database(admin) as engine:
        run(engine, keys)
    print(f"\nlab database dropped; done at {datetime.now(UTC).strftime('%H:%M:%S')} UTC")


if __name__ == "__main__":
    main()
