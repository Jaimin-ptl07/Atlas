# Database Experiments

Controlled experiments against the Atlas dev stack. Requires
`ATLAS_EXPERIMENTS_ENABLED=true` in `server/.env` (routes are mounted
only when the flag is on; production never sees them).

## Endpoints (flag-gated)

| Route | Purpose |
|---|---|
| `GET /experiment/read/{id}` | instrumented read: times connection acquisition vs query |
| `GET /experiment/metrics` | registry snapshot: requests, pool gauges, timings, pg connections |
| `POST /experiment/reset` | zero the registry between runs |

## Experiment 1 — read workload (20 / 100 / 500 QPS)

```bash
# 0. flag already in server/.env; apply it
docker compose -f compose.yaml -f compose.dev.yaml up -d --force-recreate server

# 1. seed data (ids 1..N)
cd server && uv run python -m experiments.seed --count 1000

# 2. reset metrics, run 20 QPS for 30s
curl -s -X POST http://localhost:8000/experiment/reset
uv run python -m experiments.load_test --qps 20 --duration 30 --max-id 1000

# 3. repeat at higher pressure
curl -s -X POST http://localhost:8000/experiment/reset
uv run python -m experiments.load_test --qps 100 --duration 30 --max-id 1000
```

## Watching Postgres directly (during a run)

```bash
docker exec atlas-postgres-1 psql -U atlas -d atlas -c \
  "SELECT count(*), state FROM pg_stat_activity WHERE datname='atlas' GROUP BY state;"
```

## Notes

- The load generator is an OPEN loop: arrivals are fixed by `--qps`
  regardless of completion speed — queueing pressure is realistic.
- `/experiment/metrics`'s own query holds a connection while counting
  `pg_stat_activity`, inflating that number by one.
- Results (JSON with per-second server samples) land in `results/` (gitignored).
