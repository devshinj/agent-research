# deploy/build.ps1 - Build and export Docker images for deployment
param(
    [string]$ServerIP = "192.168.102.150",
    [int]$WebPort = 3001
)

$ErrorActionPreference = "Stop"

$ApiUrl = "http://${ServerIP}:${WebPort}"
$WsUrl = "ws://${ServerIP}:${WebPort}"

Write-Host "=== Building API image ===" -ForegroundColor Cyan
docker build --platform linux/amd64 --target app -t agent-research-app:latest -f deploy/Dockerfile .
if ($LASTEXITCODE -ne 0) { throw "API build failed" }

Write-Host "=== Building Web image ===" -ForegroundColor Cyan
docker build --platform linux/amd64 --target web -t agent-research-web:latest `
    --build-arg VITE_API_URL=$ApiUrl `
    --build-arg VITE_WS_URL=$WsUrl `
    -f deploy/Dockerfile .
if ($LASTEXITCODE -ne 0) { throw "Web build failed" }

Write-Host "=== Saving images ===" -ForegroundColor Cyan

function Save-DockerImageGzip([string]$ImageName, [string]$OutputFile) {
    $tarFile = $OutputFile -replace '\.gz$', ''
    docker save $ImageName -o $tarFile
    if ($LASTEXITCODE -ne 0) { throw "docker save failed for $ImageName" }

    $inStream = [System.IO.File]::OpenRead($tarFile)
    $outStream = [System.IO.File]::Create($OutputFile)
    $gzip = [System.IO.Compression.GZipStream]::new($outStream, [System.IO.Compression.CompressionLevel]::Optimal)
    $inStream.CopyTo($gzip)
    $gzip.Dispose(); $outStream.Dispose(); $inStream.Dispose()
    Remove-Item $tarFile
}

Save-DockerImageGzip "agent-research-app:latest" "deploy/agent-research-app.tar.gz"
Save-DockerImageGzip "agent-research-web:latest" "deploy/agent-research-web.tar.gz"

Write-Host "=== Done ===" -ForegroundColor Green
Write-Host "Output files:"
Get-Item deploy/agent-research-app.tar.gz, deploy/agent-research-web.tar.gz | Format-Table Name, @{N="Size(MB)";E={[math]::Round($_.Length/1MB,1)}}
1