"""Open-loop load generator for database experiments.

Usage:
    uv run python experiments/load_test.py --qps 20 --duration 30 --max-id 1000

OPEN loop: a new request is scheduled every 1/qps seconds no matter how
slow previous ones are — latency growth therefore shows up as it would
under real arrival pressure. A closed loop (fixed worker count) would
silently slow the arrival rate instead.

Measures client-side: latency percentiles, actual throughput, max
concurrent in-flight requests. Samples /experiment/metrics every second
for server-side pool/query/acquisition stats.
"""

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx


def _percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    rank = min(len(sorted_values) - 1, round(fraction * (len(sorted_values) - 1)))
    return sorted_values[rank]


def _ms_summary(values_seconds: list[float]) -> dict:
    ordered = sorted(v * 1000.0 for v in values_seconds)
    count = len(ordered)
    return {
        "count": count,
        "avg_ms": round(sum(ordered) / count, 3) if count else 0.0,
        "p50_ms": round(_percentile(ordered, 0.50), 3),
        "p95_ms": round(_percentile(ordered, 0.95), 3),
        "p99_ms": round(_percentile(ordered, 0.99), 3),
    }


class RunStats:
    def __init__(self) -> None:
        self.latencies: list[float] = []
        self.statuses: dict[int, int] = {}
        self.errors = 0
        self.in_flight = 0
        self.max_in_flight = 0
        self.samples: list[dict] = []

    def request_done(self, latency: float, status_code: int | None) -> None:
        self.latencies.append(latency)
        if status_code is None:
            self.errors += 1
        else:
            self.statuses[status_code] = self.statuses.get(status_code, 0) + 1

    def snapshot(self) -> dict:
        return {
            "requests": {
                "sent": len(self.latencies),
                "statuses": self.statuses,
                "transport_errors": self.errors,
                "max_concurrency": self.max_in_flight,
            },
            "latency": _ms_summary(self.latencies),
        }


async def run_load(base_url: str, qps: float, duration: float, max_id: int) -> RunStats:
    stats = RunStats()

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        lock = asyncio.Lock()

        async def one_request() -> None:
            async with lock:
                stats.in_flight += 1
                stats.max_in_flight = max(stats.max_in_flight, stats.in_flight)
            started = time.perf_counter()
            status_code: int | None = None
            try:
                response = await client.get(f"/experiment/read/{_random_id(max_id)}")
                status_code = response.status_code
            except httpx.HTTPError:
                status_code = None
            finally:
                stats.request_done(time.perf_counter() - started, status_code)
                async with lock:
                    stats.in_flight -= 1

        async def sampler() -> None:
            while True:
                await asyncio.sleep(1.0)
                try:
                    response = await client.get("/experiment/metrics")
                    stats.samples.append(response.json())
                except httpx.HTTPError:
                    continue

        sampler_task = asyncio.create_task(sampler())
        started = time.perf_counter()
        scheduled = 0
        try:
            while True:
                target = started + scheduled / qps
                now = time.perf_counter()
                if target - started >= duration:
                    break
                await asyncio.sleep(max(0.0, target - now))
                asyncio.create_task(one_request())
                scheduled += 1
        finally:
            # let stragglers finish (up to 10s grace)
            deadline = time.perf_counter() + 10.0
            while len(stats.latencies) < scheduled and time.perf_counter() < deadline:
                await asyncio.sleep(0.05)
            sampler_task.cancel()

    return stats


def _random_id(max_id: int) -> int:
    import random

    return random.randint(1, max_id)


def print_report(stats: RunStats, qps: float, duration: float, wall: float) -> None:
    snap = stats.snapshot()
    lat = snap["latency"]
    reqs = snap["requests"]
    print("=" * 62)
    print(f"  LOAD RUN  target {qps:g} qps x {duration:g}s   (wall {wall:.1f}s)")
    print("=" * 62)
    print(f"requests sent          : {reqs['sent']}")
    print(f"status codes           : {reqs['statuses']}")
    print(f"transport errors       : {reqs['transport_errors']}")
    print(f"actual throughput      : {reqs['sent'] / wall:.1f} req/s")
    print(f"max concurrency        : {reqs['max_concurrency']}")
    print(f"latency p50 / p95 / p99: {lat['p50_ms']} / {lat['p95_ms']} / {lat['p99_ms']} ms")
    print(f"latency avg            : {lat['avg_ms']} ms")

    if stats.samples:
        final = stats.samples[-1]
        pool = final.get("pool", {})
        timings = final.get("timings", {})
        print("-" * 62)
        print("server (cumulative since last /experiment/reset):")
        print(f"pool size / max overflow : {pool.get('size')} / {pool.get('max_overflow')}")
        print(f"max checked out         : {pool.get('max_checked_out')}")
        print(f"new db connections      : {pool.get('connections_created')}")
        print(f"postgres connections    : {final.get('postgres_connections')}")
        acq = timings.get("acquisition_ms", {})
        qry = timings.get("query_ms", {})
        print(
            f"acquisition p50/p95     : {acq.get('p50')} / {acq.get('p95')} ms "
            f"(n={acq.get('count')})"
        )
        print(f"query time    p50/p95   : {qry.get('p50')} / {qry.get('p95')} ms (n={qry.get('count')})")
        srv = final.get("requests", {})
        print(f"server max in-flight    : {srv.get('max_in_flight')}")
    print("=" * 62)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--qps", type=float, default=20.0)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--max-id", type=int, default=1000)
    args = parser.parse_args()

    wall_started = time.perf_counter()
    stats = asyncio.run(run_load(args.url, args.qps, args.duration, args.max_id))
    wall = time.perf_counter() - wall_started

    print_report(stats, args.qps, args.duration, wall)

    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output = results_dir / f"{stamp}_qps{int(args.qps)}.json"
    output.write_text(
        json.dumps(
            {
                "config": {"qps": args.qps, "duration": args.duration, "max_id": args.max_id},
                "wall_seconds": wall,
                **stats.snapshot(),
                "server_samples": stats.samples,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"results saved -> {output}")


if __name__ == "__main__":
    main()
