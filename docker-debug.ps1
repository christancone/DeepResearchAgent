# PowerShell debug script for Docker issues

Write-Host "=== Docker Debug Information ===" -ForegroundColor Cyan
Write-Host ""

Write-Host "1. Checking Docker status..." -ForegroundColor Yellow
docker ps -a | Select-String "asset-research-agent"
Write-Host ""

Write-Host "2. Checking build progress..." -ForegroundColor Yellow
docker compose logs --tail=50 asset-research-agent 2>&1
Write-Host ""

Write-Host "3. Checking if container is running..." -ForegroundColor Yellow
$running = docker ps | Select-String "asset-research-agent"
if ($running) {
    Write-Host "✓ Container is running" -ForegroundColor Green
    Write-Host ""
    Write-Host "4. Testing container access..." -ForegroundColor Yellow
    docker compose exec asset-research-agent echo "Container is accessible"
} else {
    Write-Host "✗ Container is not running" -ForegroundColor Red
    Write-Host ""
    Write-Host "4. Checking why container stopped..." -ForegroundColor Yellow
    docker compose ps
    Write-Host ""
    Write-Host "5. Recent logs:" -ForegroundColor Yellow
    docker compose logs --tail=100 asset-research-agent
}

Write-Host ""
Write-Host "=== Debug Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Yellow
Write-Host "  docker compose logs -f asset-research-agent  # Follow logs"
Write-Host "  docker compose build --progress=plain          # Build with verbose output"
Write-Host "  docker compose up --build --no-deps           # Rebuild without dependencies"
