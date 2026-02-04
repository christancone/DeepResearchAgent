# Docker Commands Guide

## Development Mode (Fast rebuilds, code mounted as volume)

**Use this for daily development** - code changes don't require rebuild!

### First time setup:
```powershell
docker compose -f docker-compose.dev.yml up --build -d
```

### After dependency changes (pyproject.toml, requirements.txt):
```powershell
docker compose -f docker-compose.dev.yml up --build -d
```

### After code changes only (src/, examples/, main.py):
**No rebuild needed!** Code is mounted as volume, changes are live immediately.

### Run commands:
```powershell
# Interactive shell
docker compose -f docker-compose.dev.yml exec asset-research-agent-dev bash

# Run example
docker compose -f docker-compose.dev.yml exec asset-research-agent-dev python examples/run_asset_research.py --help

# View logs
docker compose -f docker-compose.dev.yml logs -f
```

### Stop:
```powershell
docker compose -f docker-compose.dev.yml down
```

---

## Production Mode (Clean installation, optimized image)

**Use this for production deployments** - clean, reproducible builds.

### Build and run:
```powershell
docker compose up --build -d
```

### Run commands:
```powershell
# Interactive shell
docker compose exec asset-research-agent bash

# Run example
docker compose exec asset-research-agent python examples/run_asset_research.py --help

# View logs
docker compose logs -f
```

### Stop:
```powershell
docker compose down
```

---

## Key Differences

| Feature | Development | Production |
|---------|------------|------------|
| **Dockerfile** | `Dockerfile.dev` | `Dockerfile` |
| **Compose file** | `docker-compose.dev.yml` | `docker-compose.yml` |
| **Code mounting** | ✅ Yes (live changes) | ❌ No (baked in) |
| **poetry lock** | Uses existing (faster) | Regenerates (clean) |
| **Rebuild time** | ~2-5 min (if deps change) | ~30+ min (always clean) |
| **Code changes** | Instant (no rebuild) | Requires rebuild |
| **Use case** | Daily development | Production/deployment |

---

## Tips

1. **Development**: Use `docker-compose.dev.yml` for daily work
2. **Dependency changes**: Rebuild dev container when `pyproject.toml` changes
3. **Code changes**: No rebuild needed in dev mode - just restart if needed
4. **Production**: Use regular `docker-compose.yml` for final builds
