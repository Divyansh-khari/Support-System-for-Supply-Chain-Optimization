# Cloud-Native Decision Support System for Supply Chain Optimization

Cloud Computing course project, IIT Delhi. Team: Divyansh Khari, Himanshu Rao.

We compare a monolith with microservices, and several autoscaling policies, on
Azure Container Apps, using a supply-allocation optimizer as the workload.

## Status

- [x] Phase 1: allocation workload (`scm_core/`) and tests
- [x] Phase 2: services (API, optimization, simulation)
- [x] Phase 3: Docker, local test
- [ ] Phase 4: Azure deployment
- [ ] Phase 5: monitoring and load testing
- [ ] Phase 6: experiments A, B, C
- [ ] Phase 7: analysis and report

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest                     # 8 tests should pass
python scripts/demo.py     # see what each part produces
```

## Run with Docker

One image runs as any service; `SERVICE` picks which. Both setups get the
same total CPU (1.5) so Experiment A is a fair comparison.

```bash
docker compose --profile monolith up --build        # API on http://127.0.0.1:8000
docker compose --profile microservices up --build   # API on http://127.0.0.1:8080
python scripts/try_api.py http://127.0.0.1:8080     # in a second terminal
docker compose --profile microservices down         # stop and remove
```

The first request to each fresh container is slow (warm-up); load tests
must exclude a warm-up period from the results.

## Layout

| Path | What it is |
|---|---|
| `scm_core/data.py` | Builds a reproducible problem from (warehouses, stores, seed) |
| `scm_core/optimizer.py` | Minimum-cost allocation as a linear program (PuLP + HiGHS) |
| `scm_core/simulation.py` | Monte Carlo demand scenarios, each re-solved |
| `scripts/demo.py` | Runs each part and prints readable output |
| `tests/test_core.py` | Correctness tests, including a cross-check against SciPy |
