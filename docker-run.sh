#!/bin/bash
# Helper script to run asset research agent commands in Docker

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Asset Research Agent - Docker Helper${NC}"
echo ""

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    if command -v docker &> /dev/null && docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    else
        echo "Error: docker-compose or docker compose not found"
        exit 1
    fi
else
    DOCKER_COMPOSE="docker-compose"
fi

# Function to run command in container
run_in_container() {
    $DOCKER_COMPOSE exec asset-research-agent python examples/run_asset_research.py "$@"
}

# Parse command
case "$1" in
    build)
        echo -e "${GREEN}Building Docker image...${NC}"
        $DOCKER_COMPOSE build
        ;;
    up)
        echo -e "${GREEN}Starting container...${NC}"
        $DOCKER_COMPOSE up -d
        echo -e "${GREEN}Container is running. Use './docker-run.sh run <args>' to execute commands${NC}"
        ;;
    down)
        echo -e "${GREEN}Stopping container...${NC}"
        $DOCKER_COMPOSE down
        ;;
    shell)
        echo -e "${GREEN}Opening shell in container...${NC}"
        $DOCKER_COMPOSE exec asset-research-agent /bin/bash
        ;;
    run|"")
        if [ "$1" = "run" ]; then
            shift
        fi
        echo -e "${GREEN}Running asset research agent...${NC}"
        run_in_container "$@"
        ;;
    logs)
        $DOCKER_COMPOSE logs -f asset-research-agent
        ;;
    *)
        echo "Usage: $0 [build|up|down|shell|run|logs] [args...]"
        echo ""
        echo "Commands:"
        echo "  build              - Build Docker image"
        echo "  up                 - Start container in background"
        echo "  down               - Stop container"
        echo "  shell              - Open interactive shell"
        echo "  run [args...]      - Run asset research agent (default)"
        echo "  logs               - Show container logs"
        echo ""
        echo "Examples:"
        echo "  $0 build"
        echo "  $0 up"
        echo "  $0 run --asset-id test-001 --prompt 'List components'"
        echo "  $0 shell"
        exit 1
        ;;
esac
