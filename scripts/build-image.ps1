param(
    [string]$Image = 'flipkart-scraper:1.0.2',
    [switch]$Export
)

$ErrorActionPreference = 'Stop'
$imageWorkspace = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $imageWorkspace
try {
    docker build --platform linux/amd64 --build-arg APP_VERSION=1.0.2 --tag $Image .
    if ($LASTEXITCODE -ne 0) { throw 'Docker build failed.' }

    Get-Content -LiteralPath (Join-Path $PSScriptRoot 'container_smoke.py') -Raw |
        docker run --rm -i --init --entrypoint python $Image -
    if ($LASTEXITCODE -ne 0) { throw 'Container smoke check failed.' }

    if ($Export) {
        $imageOutputDir = Join-Path $imageWorkspace 'dist'
        New-Item -ItemType Directory -Path $imageOutputDir -Force | Out-Null
        $imageArchive = Join-Path $imageOutputDir 'flipkart-scraper-1.0.2-linux-amd64.tar'
        docker image save --output $imageArchive $Image
        if ($LASTEXITCODE -ne 0) { throw 'Docker image export failed.' }
        $imageHash = Get-FileHash -LiteralPath $imageArchive -Algorithm SHA256
        "$($imageHash.Hash.ToLower())  $(Split-Path -Leaf $imageArchive)" |
            Set-Content -LiteralPath ($imageArchive + '.sha256') -Encoding ASCII
        Write-Output "Image archive: $imageArchive"
    }
} finally {
    Pop-Location
}
