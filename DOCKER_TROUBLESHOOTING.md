# Docker Troubleshooting Guide

## Error: "invalid rootfs: stat /run/desktop-containerd/daemon/... no such file or directory"

This is a Docker Desktop issue, not a problem with your Dockerfile. Try these solutions:

### Solution 1: Restart Docker Desktop (Quick Fix)
1. Right-click Docker Desktop icon in system tray
2. Click "Restart"
3. Wait for Docker to fully restart
4. Try again: `docker compose up --build -d`

### Solution 2: Clean Up Docker Resources
```powershell
# Stop all containers
docker compose down

# Remove the problematic container
docker rm -f asset-research-agent

# Remove the image
docker rmi deepresearchagent-asset-research-agent:latest

# Prune unused resources
docker system prune -a --volumes

# Try again
docker compose up --build -d
```

### Solution 3: Reset Docker Desktop (Nuclear Option)
If above doesn't work:
1. Open Docker Desktop
2. Go to Settings → Troubleshoot
3. Click "Clean / Purge data"
4. Or: Settings → Reset to factory defaults
5. Restart Docker Desktop
6. Rebuild: `docker compose up --build -d`

### Solution 4: Check Docker Desktop Storage
1. Open Docker Desktop
2. Go to Settings → Resources → Advanced
3. Check if disk space is available
4. Increase disk image size if needed

### Solution 5: Use WSL 2 Backend (Recommended for Windows)
1. Open Docker Desktop Settings
2. Go to General
3. Enable "Use the WSL 2 based engine"
4. Apply & Restart

---

## Quick Fix Commands

```powershell
# Quick cleanup and restart
docker compose down
docker system prune -f
docker compose up --build -d
```

---

## Alternative: Use Development Mode

If production build keeps failing, try development mode which is more stable:

```powershell
docker compose -f docker-compose.dev.yml up --build -d
```
