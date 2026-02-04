#!/bin/bash
# Quick setup script for Ubuntu/Linux

set -e  # Exit on error

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Asset Research Agent - Ubuntu Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if running on Ubuntu/Debian
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo -e "${YELLOW}Warning: Cannot detect OS. Continuing anyway...${NC}"
    OS="unknown"
fi

echo -e "${GREEN}Step 1: Checking prerequisites...${NC}"

# Check Docker
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✓ Docker is installed${NC}"
    DOCKER_AVAILABLE=true
else
    echo -e "${YELLOW}✗ Docker not found${NC}"
    DOCKER_AVAILABLE=false
fi

# Check Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    echo -e "${GREEN}✓ Python $PYTHON_VERSION is installed${NC}"
    PYTHON_AVAILABLE=true
else
    echo -e "${YELLOW}✗ Python3 not found${NC}"
    PYTHON_AVAILABLE=false
fi

function setup_docker() {
    echo ""
    echo -e "${GREEN}Setting up Docker...${NC}"
    
    if [ "$DOCKER_AVAILABLE" = false ]; then
        echo -e "${YELLOW}Installing Docker...${NC}"
        if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
            sudo apt-get update
            sudo apt-get install -y docker.io docker-compose
            sudo usermod -aG docker $USER
            echo -e "${GREEN}✓ Docker installed. Please log out and back in for group changes.${NC}"
        else
            echo -e "${YELLOW}Please install Docker manually for your OS.${NC}"
            exit 1
        fi
    fi
    
    # Make scripts executable
    chmod +x docker-run.sh
    
    # Create outputs directory
    mkdir -p outputs
    chmod 755 outputs
    
    # Check .env file
    if [ ! -f .env ]; then
        echo -e "${YELLOW}Creating .env from template...${NC}"
        if [ -f .env.template ]; then
            cp .env.template .env
            echo -e "${YELLOW}Please edit .env file with your API keys!${NC}"
        fi
    fi
    
    echo ""
    echo -e "${GREEN}Docker setup complete!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Edit .env file with your API keys"
    echo "  2. Run: ./docker-run.sh build"
    echo "  3. Run: ./docker-run.sh up"
    echo "  4. Run: ./docker-run.sh run --asset-id test-001 --prompt 'List components'"
}

function setup_native() {
    echo ""
    echo -e "${GREEN}Setting up Native Python environment...${NC}"
    
    if [ "$PYTHON_AVAILABLE" = false ]; then
        echo -e "${YELLOW}Installing Python 3.11+...${NC}"
        if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
            sudo apt-get update
            sudo apt-get install -y python3.11 python3.11-venv python3-pip
        else
            echo -e "${YELLOW}Please install Python 3.11+ manually for your OS.${NC}"
            exit 1
        fi
    fi
    
    # Install system dependencies
    echo -e "${GREEN}Installing system dependencies...${NC}"
    if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
        sudo apt-get update
        sudo apt-get install -y \
            build-essential \
            gcc \
            g++ \
            postgresql-client \
            libpq-dev \
            python3-dev \
            libffi-dev \
            libssl-dev
    fi
    
    # Create virtual environment
    echo -e "${GREEN}Creating virtual environment...${NC}"
    python3 -m venv venv
    
    # Activate and install packages
    echo -e "${GREEN}Installing Python packages...${NC}"
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    
    # Create outputs directory
    mkdir -p outputs
    chmod 755 outputs
    
    # Check .env file
    if [ ! -f .env ]; then
        echo -e "${YELLOW}Creating .env from template...${NC}"
        if [ -f .env.template ]; then
            cp .env.template .env
            echo -e "${YELLOW}Please edit .env file with your API keys!${NC}"
        fi
    fi
    
    echo ""
    echo -e "${GREEN}Native Python setup complete!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Edit .env file with your API keys"
    echo "  2. Activate venv: source venv/bin/activate"
    echo "  3. Run: python examples/run_asset_research.py --asset-id test-001 --prompt 'List components'"
}

echo ""
echo -e "${BLUE}Choose setup method:${NC}"
echo "1) Docker (Recommended - Easiest)"
echo "2) Native Python (Virtual Environment)"
echo "3) Both"
read -p "Enter choice [1-3]: " choice

case $choice in
    1)
        setup_docker
        ;;
    2)
        setup_native
        ;;
    3)
        setup_docker
        setup_native
        ;;
    *)
        echo -e "${YELLOW}Invalid choice. Exiting.${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
