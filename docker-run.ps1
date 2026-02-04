# PowerShell helper script to run asset research agent commands in Docker

param(
    [Parameter(Position=0)]
    [string]$Command = "run",
    
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Args
)

# Colors for output
function Write-ColorOutput {
    param([string]$Message, [string]$Color = "White")
    Write-Host $Message -ForegroundColor $Color
}

Write-ColorOutput "Asset Research Agent - Docker Helper" "Cyan"
Write-Host ""

# Check if docker-compose is available
$dockerCompose = "docker-compose"
if (-not (Get-Command docker-compose -ErrorAction SilentlyContinue)) {
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        $dockerCompose = "docker compose"
    } else {
        Write-ColorOutput "Error: docker-compose or docker compose not found" "Red"
        exit 1
    }
}

# Function to run command in container
function Run-InContainer {
    param([string[]]$Arguments)
    & $dockerCompose.Split(' ') exec asset-research-agent python examples/run_asset_research.py $Arguments
}

# Parse command
switch ($Command.ToLower()) {
    "build" {
        Write-ColorOutput "Building Docker image..." "Green"
        & $dockerCompose.Split(' ') build
    }
    "up" {
        Write-ColorOutput "Starting container..." "Green"
        & $dockerCompose.Split(' ') up -d
        Write-ColorOutput "Container is running. Use './docker-run.ps1 run <args>' to execute commands" "Green"
    }
    "down" {
        Write-ColorOutput "Stopping container..." "Green"
        & $dockerCompose.Split(' ') down
    }
    "shell" {
        Write-ColorOutput "Opening shell in container..." "Green"
        & $dockerCompose.Split(' ') exec asset-research-agent /bin/bash
    }
    "run" {
        Write-ColorOutput "Running asset research agent..." "Green"
        Run-InContainer -Arguments $Args
    }
    "logs" {
        & $dockerCompose.Split(' ') logs -f asset-research-agent
    }
    default {
        Write-Host "Usage: .\docker-run.ps1 [build|up|down|shell|run|logs] [args...]"
        Write-Host ""
        Write-Host "Commands:"
        Write-Host "  build              - Build Docker image"
        Write-Host "  up                 - Start container in background"
        Write-Host "  down               - Stop container"
        Write-Host "  shell              - Open interactive shell"
        Write-Host "  run [args...]      - Run asset research agent (default)"
        Write-Host "  logs               - Show container logs"
        Write-Host ""
        Write-Host "Examples:"
        Write-Host "  .\docker-run.ps1 build"
        Write-Host "  .\docker-run.ps1 up"
        Write-Host "  .\docker-run.ps1 run --asset-id test-001 --prompt 'List components'"
        Write-Host "  .\docker-run.ps1 shell"
        exit 1
    }
}
