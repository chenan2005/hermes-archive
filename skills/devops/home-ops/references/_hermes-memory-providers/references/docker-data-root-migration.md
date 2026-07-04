# Docker Data-Root Migration for Hindsight

When Hindsight's Docker image (~6.4GB) plus its data volume grows, the default data-root (`/var/lib/docker`) may be on a small system partition. This guide moves Docker to a larger partition.

## Procedure

### 1. Check Current Layout

```bash
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT,LABEL
df -h -x tmpfs
sudo docker info | grep "Docker Root Dir"
sudo docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Size}}"
sudo docker images
sudo docker volume ls
```

### 2. Stop Docker

```bash
sudo docker stop hindsight     # stop the container
sudo docker rm hindsight       # remove it (volume preserved)
sudo systemctl stop docker docker.socket
sudo systemctl status docker   # confirm inactive
```

### 3. Migrate Data

```bash
# Create target directory on the large partition
sudo mkdir -p /media/chenan/data/docker

# Copy existing Docker data
sudo rsync -a /var/lib/docker/ /media/chenan/data/docker/

# Verify no differences
sudo diff -rq /var/lib/docker /media/chenan/data/docker | grep "Only in" || echo "No differences"
```

### 4. Configure New Data-Root

```bash
sudo tee /etc/docker/daemon.json << 'EOF'
{
  "data-root": "/media/chenan/data/docker"
}
EOF

# Move old data out of the way
sudo mv /var/lib/docker /var/lib/docker.bak
```

### 5. Restart Docker & Recreate Hindsight

```bash
sudo systemctl start docker
sudo docker info | grep "Docker Root Dir"   # verify new path

# Recreate hindsight container
sudo docker run -d --restart unless-stopped --name hindsight \
  -p 8888:8888 -p 9999:9999 \
  --env-file /path/to/hindsight.env \
  -v /media/chenan/data/hindsight/pg0:/home/hindsight/.pg0 \
  ghcr.io/vectorize-io/hindsight:latest
```

**Important**: If using a named volume (`hindsight-data`) instead of bind mount, Docker automatically relocates it under the new `data-root` — no additional steps needed. Verify with `sudo docker volume inspect hindsight-data`.

### 6. Verify

```bash
sleep 30
curl -s http://localhost:8888/health
# Expected: {"status":"healthy","database":"connected"}
sudo docker ps --filter name=hindsight --format "table {{.Names}}\t{{.Status}}"
hermes memory status
# Expected: Provider: hindsight, Status: available ✓
```

## Clean Up Old Data

When everything is confirmed working:

```bash
sudo rm -rf /var/lib/docker.bak
```

## Pitfalls

- **Non-root user can't `docker ps`.** After migration, the user must be in the `docker` group. Changes take effect after a new login session (`sg docker -c "..."` or a new SSH/terminal).
- **Bind mount ownership.** If using a host bind mount instead of Docker volume, the path must be owned by UID 1000. Fix: `sudo chown 1000:1000 <path>`.
- **`docker ps` shows nothing without sudo even when Docker is running.** Always use `sudo docker ps` as the authoritative check.
