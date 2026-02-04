# Docker Setup Guide

Quick start guide for running the Asset Dossier Research Agent with Docker.

## Prerequisites

- Docker Desktop installed and running
- `.env` file configured with your API keys

## Quick Start

### 1. Build and Start Container

```bash
# Build and start in one command
docker compose up --build -d

# Or use the helper script (PowerShell)
.\docker-run.ps1 build
.\docker-run.ps1 up
```

### 2. Run the Agent

```bash
# Using docker compose directly
docker compose exec asset-research-agent python examples/run_asset_research.py \
  --asset-id "test-001" \
  --prompt "Extract all LLPs" \
  --verbose

# Or using helper script (PowerShell)
.\docker-run.ps1 run --asset-id "test-001" --prompt "Extract all LLPs" --verbose
```

### 3. View Logs

```bash
docker compose logs -f asset-research-agent
```

### 4. Interactive Shell

```bash
# Open bash shell in container
docker compose exec asset-research-agent /bin/bash

# Or using helper script
.\docker-run.ps1 shell
```

### 5. Stop Container

```bash
docker compose down
```

## Common Commands

### Basic Analysis
```bash
docker compose exec asset-research-agent python examples/run_asset_research.py \
  --asset-id "YOUR_ASSET_ID" \
  --prompt "List all components"
```

### Comprehensive Analysis with Streaming
```bash
docker compose exec asset-research-agent python examples/run_asset_research.py \
  --asset-id "YOUR_ASSET_ID" \
  --depth comprehensive \
  --stream \
  --verbose
```

### With Live Monitor
```bash
docker compose exec asset-research-agent python examples/run_asset_research.py \
  --asset-id "YOUR_ASSET_ID" \
  --live-monitor
```

## Output Files

Output files are saved to `./outputs/` directory, which is mounted as a volume:
- `asset_research_{asset_id}_{timestamp}.json` - Research results
- `canvas_{asset_id}_{timestamp}.json` - Working memory canvas state

## Environment Variables

The container automatically loads environment variables from your `.env` file:
- `SUPABASE_URL` - Your Supabase project URL
- `SUPABASE_SERVICE_KEY` - Supabase service role key
- `OPENAI_API_KEY` - OpenAI API key
- `ANTHROPIC_API_KEY` - Anthropic API key (optional)
- `GOOGLE_API_KEY` - Google API key (optional)
- And more...

## Troubleshooting

### Container won't start
```bash
# Check logs
docker compose logs asset-research-agent

# Rebuild from scratch
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Permission issues with outputs directory
```bash
# Fix permissions (Linux/Mac)
sudo chown -R $USER:$USER ./outputs

# Or create outputs directory first
mkdir -p outputs
```

### Environment variables not loading
- Ensure `.env` file exists in project root
- Check that variables are properly formatted (no spaces around `=`)
- Restart container after changing `.env`: `docker compose restart`

## Development Mode

For development, you can mount the source code:

```yaml
# Add to docker-compose.yml volumes section:
volumes:
  - ./src:/app/src
  - ./configs:/app/configs
```

Then rebuild: `docker compose up --build`
