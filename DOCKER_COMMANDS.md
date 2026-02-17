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

If you see "can't open file '/app/examples/run_asset_research.py'" then the image is stale — rebuild with `docker compose up --build -d`.

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

## Database connection ("No address associated with hostname")

If you see **Could not connect to database: [Errno -5] No address associated with hostname** and **Database connected: False**, the container cannot resolve the host in `DATABASE_URL`.

**If the database runs on your host machine (e.g. local PostgreSQL):**

- Inside the container, `localhost` is the container itself, not your PC.
- In `.env`, use the host’s hostname instead of `localhost`:

  **Windows/Mac (Docker Desktop):**
  ```env
  DATABASE_URL=postgresql://user:password@host.docker.internal:5432/your_db
  ```

  **Linux:** Use your machine’s IP or `host.docker.internal` if your Docker version supports it.

**If you use Supabase (or another remote DB):**

- Use the real Supabase connection string (e.g. `postgresql://...@aws-0-xx.pooler.supabase.com:6543/postgres`) in `.env`.
- Ensure the container has outbound internet and that `DATABASE_URL` is set in `.env` so compose can pass it into the container.

**Check that the variable is passed:**

```powershell
docker compose exec asset-research-agent env | findstr DATABASE
```

The app still runs with **mock asset context** (Pages: 0, Documents: 0) when the DB is unreachable; fix `DATABASE_URL` to use real data.

---

## Tips

1. **Development**: Use `docker-compose.dev.yml` for daily work
2. **Dependency changes**: Rebuild dev container when `pyproject.toml` changes
3. **Code changes**: No rebuild needed in dev mode - just restart if needed
4. **Production**: Use regular `docker-compose.yml` for final builds
