# Ubuntu/Linux Setup Guide

Complete setup guide for running the Asset Dossier Research Agent on Ubuntu/Linux.

## Option 1: Docker (Recommended - Easiest)

### Prerequisites

```bash
# Install Docker and Docker Compose
sudo apt-get update
sudo apt-get install -y docker.io docker-compose

# Add your user to docker group (to run without sudo)
sudo usermod -aG docker $USER
# Log out and back in for group changes to take effect

# Verify Docker is working
docker --version
docker-compose --version
```

### Quick Start with Docker

```bash
# Navigate to project directory
cd /path/to/DeepResearchAgent

# Build and start container
docker compose up --build -d

# Run the agent
docker compose exec asset-research-agent python examples/run_asset_research.py \
  --asset-id "test-001" \
  --prompt "List all components" \
  --verbose

# Or use the helper script
chmod +x docker-run.sh
./docker-run.sh run --asset-id "test-001" --prompt "List all components" --verbose

# View logs
docker compose logs -f asset-research-agent

# Stop container
docker compose down
```

### Using Helper Script (Linux)

```bash
# Make script executable
chmod +x docker-run.sh

# Build
./docker-run.sh build

# Start container
./docker-run.sh up

# Run agent
./docker-run.sh run --asset-id "test-001" --prompt "Extract all LLPs"

# Open shell
./docker-run.sh shell

# View logs
./docker-run.sh logs

# Stop
./docker-run.sh down
```

---

## Option 2: Native Python Setup (Without Docker)

### Step 1: Install System Dependencies

```bash
# Update package list
sudo apt-get update

# Install Python 3.11+ and build tools
sudo apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    build-essential \
    gcc \
    g++ \
    postgresql-client \
    libpq-dev \
    curl

# Verify Python version (should be 3.11+)
python3 --version
```

### Step 2: Create Virtual Environment

```bash
# Navigate to project directory
cd /path/to/DeepResearchAgent

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip
```

### Step 3: Install Python Dependencies

```bash
# Install all requirements
pip install -r requirements.txt

# Verify key packages
python3 -c "import asyncpg; import tiktoken; import pydantic; print('All packages installed!')"
```

### Step 4: Configure Environment

```bash
# Copy .env.template if .env doesn't exist
cp .env.template .env

# Edit .env with your credentials
nano .env
# Or use your preferred editor: vim, code, etc.
```

### Step 5: Test the Agent

```bash
# Make sure venv is activated (you should see (venv) in prompt)
source venv/bin/activate

# Run a test
python examples/run_asset_research.py \
  --asset-id "test-001" \
  --prompt "List all components" \
  --verbose

# Or with comprehensive analysis
python examples/run_asset_research.py \
  --asset-id "YOUR_ASSET_ID" \
  --depth comprehensive \
  --stream \
  --verbose
```

### Step 6: Create Outputs Directory

```bash
# Create outputs directory if it doesn't exist
mkdir -p outputs

# Set proper permissions
chmod 755 outputs
```

---

## Common Commands

### Activate Virtual Environment
```bash
source venv/bin/activate
```

### Deactivate Virtual Environment
```bash
deactivate
```

### Run Agent with Different Options
```bash
# Basic analysis
python examples/run_asset_research.py --asset-id "ASSET_ID" --prompt "Your question"

# Comprehensive with streaming
python examples/run_asset_research.py \
  --asset-id "ASSET_ID" \
  --depth comprehensive \
  --stream \
  --verbose

# With live monitor
python examples/run_asset_research.py \
  --asset-id "ASSET_ID" \
  --live-monitor
```

---

## Troubleshooting

### Permission Denied Errors

```bash
# Fix permissions for outputs directory
sudo chown -R $USER:$USER outputs/
chmod 755 outputs/

# Fix permissions for scripts
chmod +x docker-run.sh
```

### Python Version Issues

```bash
# Check Python version
python3 --version

# If Python 3.11+ is not default, use specific version
python3.11 -m venv venv
source venv/bin/activate
```

### Missing System Libraries

```bash
# Install PostgreSQL development libraries (for asyncpg)
sudo apt-get install -y libpq-dev

# Install other build dependencies
sudo apt-get install -y \
    python3-dev \
    libffi-dev \
    libssl-dev
```

### Docker Permission Issues

```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Log out and back in, or run:
newgrp docker

# Verify
docker ps
```

### Import Errors

```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall packages
pip install --force-reinstall -r requirements.txt

# Check Python path
echo $PYTHONPATH
export PYTHONPATH=/path/to/DeepResearchAgent:$PYTHONPATH
```

### Database Connection Issues

```bash
# Test PostgreSQL connection
psql -h your-host -U your-user -d your-database

# Check if DATABASE_URL is set correctly
echo $DATABASE_URL

# Test asyncpg connection
python3 -c "import asyncio; import asyncpg; print('asyncpg installed')"
```

---

## Quick Reference

### Docker Commands
```bash
docker compose up --build -d          # Build and start
docker compose exec asset-research-agent python examples/run_asset_research.py [args]
docker compose logs -f                 # View logs
docker compose down                    # Stop
```

### Python Commands
```bash
source venv/bin/activate               # Activate venv
pip install -r requirements.txt       # Install deps
python examples/run_asset_research.py [args]  # Run agent
deactivate                             # Deactivate venv
```

### Helper Script Commands
```bash
./docker-run.sh build                  # Build image
./docker-run.sh up                     # Start container
./docker-run.sh run [args]             # Run agent
./docker-run.sh shell                   # Open shell
./docker-run.sh logs                   # View logs
./docker-run.sh down                   # Stop container
```

---

## Recommended Workflow

1. **Clone repository**
   ```bash
   git clone <repository-url>
   cd DeepResearchAgent
   ```

2. **Choose setup method:**
   - **Docker**: `docker compose up --build -d`
   - **Native**: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`

3. **Configure environment:**
   ```bash
   cp .env.template .env
   nano .env  # Add your API keys
   ```

4. **Run agent:**
   ```bash
   # Docker
   docker compose exec asset-research-agent python examples/run_asset_research.py --asset-id "test" --prompt "List components"
   
   # Native
   python examples/run_asset_research.py --asset-id "test" --prompt "List components"
   ```

5. **Check outputs:**
   ```bash
   ls -lh outputs/
   ```
