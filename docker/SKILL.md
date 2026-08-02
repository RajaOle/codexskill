---
name: docker
description: Docker and container management skill. Trigger for anything involving Docker containers, Docker Compose, Dockerfile creation, Frigate NVR container, container logs, networking, volumes, or deployment via containers.
---

# Docker & Container Management

## Key Containers on This Machine

| Container | IP / Port | Notes |
|-----------|-----------|-------|
| Frigate NVR | `192.168.1.175:5000` | 0.17.1, OpenVINO detector |
| (add others as deployed) | | |

---

## Essential Commands

```bash
# Container lifecycle
docker ps                          # running containers
docker ps -a                       # all containers including stopped
docker start <name>
docker stop <name>
docker restart <name>
docker rm <name>                   # remove stopped container

# Logs
docker logs frigate -f             # follow Frigate logs
docker logs frigate --tail=200
docker logs frigate --since 1h

# Exec into running container
docker exec -it frigate /bin/bash
docker exec -it frigate sh

# Stats
docker stats                       # live CPU/RAM per container
docker inspect <name>              # full config JSON
```

---

## Docker Compose

```bash
# Start / stop all services
docker compose up -d               # detached
docker compose down
docker compose restart

# Rebuild after config change
docker compose up -d --force-recreate

# View compose logs
docker compose logs -f
docker compose logs frigate -f --tail=100

# Pull latest images
docker compose pull
```

### Frigate Compose (reference structure)
```yaml
version: "3.9"
services:
  frigate:
    container_name: frigate
    privileged: true
    restart: unless-stopped
    image: ghcr.io/blakeblackshear/frigate:0.17.1
    shm_size: "256mb"
    devices:
      - /dev/dri/renderD128    # Intel Iris Xe VAAPI
    volumes:
      - /etc/localtime:/etc/localtime:ro
      - /home/olekamole/frigate/config:/config
      - /home/olekamole/frigate/storage:/media/frigate
      - type: tmpfs
        target: /tmp/cache
        tmpfs:
          size: 1gb
    ports:
      - "5000:5000"
      - "8554:8554"
      - "8555:8555/tcp"
      - "8555:8555/udp"
    environment:
      FRIGATE_RTSP_PASSWORD: "${FRIGATE_RTSP_PASSWORD}"
```

---

## Volumes & Storage

```bash
# List volumes
docker volume ls
docker volume inspect <name>

# Frigate storage paths
/home/olekamole/frigate/config/    # config.yml lives here
/home/olekamole/frigate/storage/   # recordings, snapshots

# Clean up unused
docker system prune -f             # containers, networks, dangling images
docker volume prune -f             # unused volumes (careful!)
```

---

## Networking

```bash
# List Docker networks
docker network ls
docker network inspect bridge

# Frigate is on the host network or bridge
# Camera at 192.168.1.249 must be reachable from container
ping 192.168.1.249                 # check from host
docker exec frigate ping 192.168.1.249  # check from inside container
```

---

## Dockerfile Patterns

### Python 3.11 + OpenVINO base
```dockerfile
FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["python", "person_tracker8.py"]
```

### requirements.txt for CV pipeline
```
ultralytics>=8.0
openvino>=2024.0
opencv-python-headless
numpy
```

---

## Frigate-Specific

### Config reload (without full restart)
```bash
# Frigate 0.17+ supports config reload via API
curl -X POST http://192.168.1.175:5000/api/config/save \
  -H "Content-Type: application/json" \
  -d @/home/olekamole/frigate/config/config.yml

# Or just restart the container
docker restart frigate
```

### Check OpenVINO detector is running
```bash
docker logs frigate 2>&1 | grep -i "openvino\|detector\|CPU\|GPU"
# Should see: "OpenVINO: ssdlite_mobilenet_v2" or similar
```

### Known Frigate paths in container
```
/config/config.yml              # main config
/media/frigate/                 # recordings
/openvino-model/                # detector model XML
```

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Frigate won't start | `docker logs frigate` — look for config YAML errors |
| Camera stream dropping | Add `input_args: preset-rtsp-restream` to stream config |
| No detections | Check zone coordinates in config; check `required_zones` |
| VAAPI errors | `docker exec frigate vainfo` — check renderD128 mapped |
| High CPU | Confirm OpenVINO detector process running, not CPU fallback |
