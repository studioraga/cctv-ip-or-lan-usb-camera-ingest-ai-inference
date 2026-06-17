# Portability change manifest

Added environment discovery, runtime YAML generation, systemd templates and installer, portable sync, parameterized sender/API scripts, generated Prometheus configuration, and full validation instructions. Static systemd files are placeholders to prevent accidental installation of stale hardcoded paths.

---

## Step 13 portability additions

Step 13 adds portable Grafana-triggered capture sessions. New runtime variables:

```text
AI_CAMERA_CAPTURE_UDP_PORT=5001
AI_CAMERA_DATASET_ROOT=data/datasets
AI_CAMERA_CAPTURE_MAX_DURATION_SEC=7200
AI_CAMERA_CAPTURE_DEFAULT_DURATION_SEC=60
AI_CAMERA_CAPTURE_DEFAULT_FRAME_STRIDE=1
```

Docker Compose is launched with:

```bash
docker compose -f docker/docker-compose.node1.yml up -d
```

Because the compose file lives under `docker/`, these relative mounts are
required:

```yaml
../configs/runtime/prometheus.yml:/etc/prometheus/prometheus.yml:ro
./grafana/provisioning:/etc/grafana/provisioning:ro
./grafana/dashboards:/var/lib/grafana/dashboards:ro
```

Generated runtime config, datasets, validation results, and DB files should not
be committed.
