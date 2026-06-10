# Datadex Setup Script
# Run once from the DataDex directory to install everything.
#
# Usage:
#   .\setup.ps1                              # install with virtual environment (recommended)
#   .\setup.ps1 -NoVenv                      # install into global Python (skip venv)
#   .\setup.ps1 -Workspace myproject         # also create an extra named workspace

param(
    [switch]$NoVenv,
    [string]$Workspace = ""
)

$ErrorActionPreference = "Stop"

# ---- Known workspaces -------------------------------------------------------
# Update this list when adding new projects. Each entry gets a config.yaml,
# docs/, and data/ directory created automatically.
$KnownWorkspaces = @(
    @{ Name = "demo"; Description = "Demo workspace — replace with your project name" }
)

# Append any extra workspace passed via -Workspace
if ($Workspace -ne "") {
    $KnownWorkspaces += @{ Name = $Workspace; Description = "Custom workspace: $Workspace" }
}

# ---- Paths ------------------------------------------------------------------
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$DatadexDir = Join-Path $ScriptDir "datadex"
$McpJson    = Join-Path $ScriptDir ".mcp.json"
$VenvDir    = Join-Path $DatadexDir ".venv"
$Reqs       = Join-Path $DatadexDir "requirements.txt"
$WsRoot     = Join-Path $DatadexDir "workspaces"

# ---- Banner -----------------------------------------------------------------
Write-Host ""
Write-Host "  Datadex Setup" -ForegroundColor Cyan
Write-Host "  -------------------------------------------------------"

if (-not (Test-Path $DatadexDir)) {
    Write-Host "  ERROR: 'datadex' folder not found next to this script." -ForegroundColor Red
    Write-Host "  Run setup.ps1 from the DataDex directory."
    exit 1
}

# ---- Step 1: Find Python 3.10+ ----------------------------------------------
Write-Host ""
Write-Host "  [1/5] Looking for Python 3.10+..." -ForegroundColor Yellow

$pythonExe = $null
foreach ($candidate in @("python", "python3", "py")) {
    try {
        $verOutput = & $candidate --version 2>&1
        if ($verOutput -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 10) {
                $pythonExe = (Get-Command $candidate -ErrorAction Stop).Source
                Write-Host "         Found: $pythonExe  ($verOutput)" -ForegroundColor Green
                break
            } else {
                Write-Host "         Skipping $candidate ($verOutput) -- need 3.10+" -ForegroundColor DarkGray
            }
        }
    } catch { }
}

if (-not $pythonExe) {
    Write-Host ""
    Write-Host "  ERROR: Python 3.10+ not found in PATH." -ForegroundColor Red
    Write-Host "  Install it from https://python.org  or run:"
    Write-Host "    winget install Python.Python.3.14"
    exit 1
}

# ---- Step 2: Virtual environment --------------------------------------------
Write-Host ""
if ($NoVenv) {
    $targetPython = $pythonExe
    Write-Host "  [2/5] Skipping virtual environment (-NoVenv)" -ForegroundColor DarkGray
} else {
    Write-Host "  [2/5] Setting up virtual environment..." -ForegroundColor Yellow
    if (Test-Path (Join-Path $VenvDir "Scripts\python.exe")) {
        Write-Host "         .venv already exists -- reusing" -ForegroundColor DarkGray
    } else {
        & $pythonExe -m venv $VenvDir
        Write-Host "         Created: $VenvDir" -ForegroundColor Green
    }
    $targetPython = Join-Path $VenvDir "Scripts\python.exe"
}

# ---- Step 3: Install dependencies -------------------------------------------
Write-Host ""
Write-Host "  [3/5] Installing dependencies..." -ForegroundColor Yellow
Write-Host "         (chromadb will download the ~80 MB embedding model on first ingest)" -ForegroundColor DarkGray
Write-Host ""

& $targetPython -m pip install --upgrade pip --quiet
& $targetPython -m pip install -r $Reqs

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  ERROR: pip install failed (exit $LASTEXITCODE)." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "         Dependencies installed." -ForegroundColor Green

# ---- Step 4: Write .mcp.json with correct machine paths ---------------------
Write-Host ""
Write-Host "  [4/5] Writing .mcp.json..." -ForegroundColor Yellow

$mcpConfig = @{
    mcpServers = @{
        datadex = [ordered]@{
            command = $targetPython.Replace("\", "/")
            args    = @("datadex_server.py")
            cwd     = $DatadexDir
        }
    }
}
$mcpConfig | ConvertTo-Json -Depth 5 | Set-Content -Path $McpJson -Encoding utf8

Write-Host "         Written: $McpJson" -ForegroundColor Green

# ---- Step 5: Create / verify workspace directories -------------------------
Write-Host ""
Write-Host "  [5/5] Setting up workspaces..." -ForegroundColor Yellow

foreach ($ws in $KnownWorkspaces) {
    $wsName    = $ws.Name
    $wsDesc    = $ws.Description
    $wsDir     = Join-Path $WsRoot $wsName
    $wsDocs    = Join-Path $wsDir "docs"
    $wsData    = Join-Path $wsDir "data"
    $wsConfig  = Join-Path $wsDir "config.yaml"

    $created = $false

    if (-not (Test-Path $wsDocs)) {
        New-Item -ItemType Directory -Force -Path $wsDocs | Out-Null
        $created = $true
    }
    if (-not (Test-Path $wsData)) {
        New-Item -ItemType Directory -Force -Path $wsData | Out-Null
        $created = $true
    }

    # Write config.yaml if missing
    if (-not (Test-Path $wsConfig)) {
        @"
workspace: "$wsName"
description: "$wsDesc"
docs_path: ./docs
data_path: ./data
"@ | Set-Content -Path $wsConfig -Encoding utf8
        $created = $true
    }

    if ($created) {
        Write-Host "         Created workspace: workspaces\$wsName\" -ForegroundColor Green
    } else {
        Write-Host "         Workspace exists: workspaces\$wsName\" -ForegroundColor DarkGray
    }
}

# ---- Done -------------------------------------------------------------------
Write-Host ""
Write-Host "  -------------------------------------------------------"
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Workspaces:"
foreach ($ws in $KnownWorkspaces) {
    Write-Host "    - $($ws.Name.PadRight(12)) datadex\workspaces\$($ws.Name)\docs\"
}
Write-Host ""
Write-Host "  Next steps:"
Write-Host ""
Write-Host "    1. Drop your datasheets into the matching workspace docs\ folder."
Write-Host "       Supported: .pdf  .docx  .xlsx  .md"
Write-Host ""
Write-Host "    2. Ingest (run from the datadex\ folder):"
if ($NoVenv) {
    Write-Host "         python datadex.py ingest --workspace <name>"
} else {
    Write-Host "         .\.venv\Scripts\python.exe datadex.py ingest --workspace <name>"
}
Write-Host ""
Write-Host "    3. Restart Claude Code -- Datadex connects automatically."
Write-Host ""
