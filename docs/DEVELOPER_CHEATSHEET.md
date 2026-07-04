# Developer Cheatsheet — juniper-deploy

**Version**: 1.2.0
**Date**: 2026-04-06
**Project**: juniper-deploy

---

## Common Commands

| Command | Description |
|---------|-------------|
| `make up` | Start full stack (all real services) |
| `make demo` | Start demo profile (auto-configured training) |
| `make dev` | Start dev profile (canopy in demo mode) |
| `make down` | Stop all containers (all profiles) |
| `make restart` | Restart all services |
| `make build` | Build/rebuild all images |
| `make build-no-cache` | Full rebuild without Docker cache |
| `make logs` | Tail all service logs (follow) |
| `make status` | Show container status |
| `make health` | Detailed health report |
| `make wait` | Block until all services healthy (90s timeout) |
| `make clean` | Remove containers, volumes, local images |
| `make logs-data` / `make logs-cascor` / `make logs-canopy` | Tail per-service logs |
| `make shell-data` / `make shell-cascor` / `make shell-canopy` | Exec into container |
| `docker compose --profile full config` | Validate compose configuration |

> See: [docs/REFERENCE.md](REFERENCE.md#makefile-targets) for complete Makefile reference.

---

## Docker Compose Profiles

| Profile | Command | Services |
|---------|---------|----------|
| `full` | `make up` | juniper-data, juniper-cascor, juniper-canopy, juniper-cascor-worker |
| `demo` | `make demo` | juniper-data, juniper-cascor-demo, juniper-canopy-demo, demo-seed |
| `dev` | `make dev` | juniper-data, juniper-cascor, juniper-canopy-dev |
| `observability` | `make obs` | prometheus (9090), alertmanager (9093), grafana (3001 host / 3000 container) |

Profiles can be combined: `docker compose --profile full --profile observability up -d`

> See: [docs/REFERENCE.md](REFERENCE.md#profile-reference) for full profile details.

---

## Service Ports

| Service | Host Port | Container Port | Health Endpoint |
|---------|-----------|----------------|-----------------|
| juniper-data | 8100 | 8100 | `/v1/health` |
| juniper-cascor | 8201 | 8200 | `/v1/health` |
| juniper-canopy | 8050 | 8050 | `/v1/health` |
| Prometheus | 9090 | 9090 | -- |
| AlertManager | 9093 | 9093 | -- |
| Grafana | 3001 | 3000 | -- |

---

## Service Dependency Chain

```
juniper-canopy (8050) --> juniper-cascor (8200) --> juniper-data (8100)
                      \                         /
                       +-------> juniper-data --+
juniper-cascor-worker  --> juniper-cascor (8200, WebSocket)
```

All `depends_on` use `condition: service_healthy` so containers wait for upstream health checks.

---

## Health Checks and Docker Networking

```bash
curl -s http://localhost:8100/v1/health | python -m json.tool          # single service
for port in 8100 8200 8050; do curl -sf http://localhost:$port/v1/health | python -m json.tool; done
make health   # formatted report across all services
```

Each service exposes `/v1/health`, `/v1/health/live`, and `/v1/health/ready`.

Services are segmented across four Docker bridge networks:

| Network | Type | Services | Purpose |
|---------|------|----------|---------|
| `frontend` | bridge | canopy, canopy-demo, canopy-dev, prometheus | Public-facing dashboard path plus Prometheus scrape access |
| `backend` | bridge, internal | cascor, cascor-demo, canopy, canopy-demo, redis, prometheus | CasCor API and internal backend traffic |
| `data` | bridge, internal | data, cascor, cascor-demo, canopy, canopy-demo, prometheus | Dataset service network; not reachable from frontend directly |
| `monitoring` | bridge | prometheus, alertmanager, grafana | Observability-only network for monitoring components |

This architecture provides network segmentation: juniper-data is only accessible from the backend services, not directly from the frontend.

| Service Name | Internal URL | Host URL | Networks |
|-------------|--------------|----------|----------|
| `juniper-data` | `http://juniper-data:8100` | `http://localhost:8100` | data |
| `juniper-cascor` | `http://juniper-cascor:8200` | `http://localhost:8201` | backend, data |
| `juniper-canopy` | `http://juniper-canopy:8050` | `http://localhost:8050` | frontend, backend, data |
| `prometheus` | `http://prometheus:9090` | `http://localhost:9090` | monitoring, backend, data, frontend |
| `grafana` | `http://grafana:3000` | `http://localhost:3001` | monitoring |

Inter-service communication uses container DNS names (e.g., `JUNIPER_DATA_URL=http://juniper-data:8100`). Host-side access uses `localhost` with mapped ports.

---

## Observability

### Start Observability Stack

```bash
docker compose --profile full --profile observability up -d
# Or:
make up && make obs
```

### Grafana

Access at `http://localhost:3001` by default (login `admin`; password from `secrets/grafana_admin_password.txt`).

### Enable Metrics Per Service

Set in `.env` or `docker-compose.yml` environment:

| Variable | Service |
|----------|---------|
| `JUNIPER_DATA_METRICS_ENABLED=true` | juniper-data |
| `JUNIPER_CASCOR_METRICS_ENABLED=true` | juniper-cascor |
| `CANOPY_METRICS_ENABLED=true` | juniper-canopy |

### Query Prometheus

```bash
curl -s 'http://localhost:9090/api/v1/query?query=juniper_data_requests_total' | python -m json.tool
```

> See: [docs/REFERENCE.md](REFERENCE.md#prometheus-configuration) and [OBSERVABILITY_GUIDE.md](OBSERVABILITY_GUIDE.md) for dashboards and metric naming.

---

## Environment Variables

### Key Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JUNIPER_DATA_URL` | `http://juniper-data:8100` | Data service URL (used by cascor) |
| `CASCOR_SERVICE_URL` | `http://juniper-cascor:8200` | CasCor service URL (used by canopy) |
| `JUNIPER_DATA_API_KEYS` | *(unset)* | API keys accepted by juniper-data |
| `JUNIPER_CASCOR_API_KEYS` | *(unset)* | API keys accepted by juniper-cascor |
| `JUNIPER_DATA_LOG_LEVEL` | `INFO` | Log level for juniper-data |
| `CASCOR_LOG_LEVEL` | `INFO` | Log level for juniper-cascor |
| `GF_SECURITY_ADMIN_PASSWORD` | `admin` | Grafana admin password |

Docker secret file variables in `docker-compose.yml`:

| Variable | Mounted Path |
|----------|--------------|
| `JUNIPER_DATA_API_KEYS_FILE` | `/run/secrets/juniper_data_api_keys` |
| `JUNIPER_CASCOR_API_KEYS_FILE` | `/run/secrets/juniper_cascor_api_keys` |
| `JUNIPER_DATA_API_KEY_FILE` | `/run/secrets/juniper_data_api_keys` |
| `CANOPY_API_KEY_FILE` | `/run/secrets/canopy_api_key` |
| `JUNIPER_CASCOR_API_KEY_FILE` | `/run/secrets/juniper_cascor_api_keys` |
| `GF_SECURITY_ADMIN_PASSWORD__FILE` | `/run/secrets/grafana_admin_password` |

Copy `.env.example` to `.env` to override defaults. All values use `${VAR:-default}` substitution.

> See: [docs/REFERENCE.md](REFERENCE.md#environment-variables) for the complete variable reference.

---

## Testing

```bash
# Start services first
make up && make wait

# Run integration tests
pip install -r requirements-test.txt
pytest tests/ -v

# Demo profile test
bash scripts/test_demo_profile.sh
```

| Test File | Purpose |
|-----------|---------|
| `tests/test_health.py` | Health endpoint + schema validation |
| `tests/test_data_service.py` | Dataset lifecycle integration |
| `tests/test_full_stack.py` | Cross-service end-to-end tests |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Container exits immediately | Missing dependency or config error | Check `docker compose logs <service>` |
| Health check failing | Service still starting | `make wait` (90s timeout); check start period |
| Port conflict | Port already in use on host | Change host port in `.env` (e.g., `CASCOR_HOST_PORT=8202`) |
| Services can't reach each other | Wrong internal URL | Verify `JUNIPER_DATA_URL` uses container name, not `localhost` |
| Prometheus shows no targets | Metrics not enabled | Set `*_METRICS_ENABLED=true` in `.env` |
| Grafana no data | Prometheus not scraping | Check `http://localhost:9090/targets` for scrape status |

---

## Kubernetes / Helm

### Helm Commands

| Command | Description |
|---------|-------------|
| `helm dependency build k8s/helm/juniper/` | Download subchart dependencies |
| `helm lint k8s/helm/juniper/` | Lint the chart |
| `helm template test k8s/helm/juniper/` | Render templates locally (no cluster) |
| `helm install juniper k8s/helm/juniper/` | Install to current cluster |
| `helm install juniper k8s/helm/juniper/ -f k8s/helm/juniper/values-production.yaml` | Install with production values |
| `helm install juniper k8s/helm/juniper/ -f k8s/helm/juniper/values-demo.yaml` | Install demo mode |
| `helm upgrade juniper k8s/helm/juniper/` | Upgrade existing release |
| `helm test juniper` | Run connectivity tests |
| `helm uninstall juniper` | Remove release |

### Integration Test (Local Cluster)

```bash
bash scripts/test_k8s.sh --driver kind         # Auto-create kind cluster, test, teardown
bash scripts/test_k8s.sh --driver minikube      # Use minikube instead
bash scripts/test_k8s.sh --no-teardown          # Keep cluster for debugging
```

### Value Overlays

| File | Use Case |
|------|----------|
| `values.yaml` | Defaults (development) |
| `values-production.yaml` | JSON logs, metrics, TLS ingress, 4-16 workers |
| `values-demo.yaml` | Auto-start training, no workers, no network policies |

> See: [docs/REFERENCE.md](REFERENCE.md#helm-chart-reference) for the full Helm chart reference.

---

## Cross-References

- [juniper-deploy REFERENCE.md](REFERENCE.md) -- Full technical reference
- [juniper-deploy AGENTS.md](../AGENTS.md) -- Agent development guide
- [OBSERVABILITY_GUIDE.md](OBSERVABILITY_GUIDE.md) -- Prometheus, Grafana, metrics
- [Ecosystem Cheatsheet](../../juniper-ml/notes/DEVELOPER_CHEATSHEET.md) -- Cross-project procedures
- [Ecosystem Guide](../../CLAUDE.md) -- Service ports, dependency graph, conventions
