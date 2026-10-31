# Creates the private Python environment for Chatterbox Voice Studio.
# Run by the installer (and by the "Repair" Start Menu shortcut). Safe to re-run: it skips work already done.
param(
    [Parameter(Mandatory = $true)][string]$AppDir,
    [switch]$PauseOnError
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Pinned so installs are reproducible. Chatterbox is installed from this exact upstream commit.
$ChatterboxCommit = '5de7a54aa4e5e2baadb0182dde554908b48b85c2'
$PerthCommit = 'ff1c8ac55a976971245cdd53c18d6131ca00d993'
$PythonVersion = '3.11'
$TorchVersion = '2.6.0'
# Standalone CPython build (pinned). We unpack it ourselves instead of letting uv do it: uv creates a directory
# junction while installing Python, which Windows 11 "Redirection Guard" blocks inside installer-launched processes.
$PythonUrl = 'https://github.com/astral-sh/python-build-standalone/releases/download/20261026/cpython-3.11.18%2B20261026-x86_64-pc-windows-msvc-install_only_stripped.tar.gz'

$Runtime = Join-Path $AppDir 'runtime'
$Venv = Join-Path $Runtime 'venv'
$Stamp = Join-Path $Runtime 'deps.stamp'
New-Item -ItemType Directory -Force $Runtime | Out-Null
Start-Transcript -Path (Join-Path $AppDir 'install.log') -Append | Out-Null

function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "'$([IO.Path]::GetFileName($Exe)) $($Arguments[0])' failed with exit code $LASTEXITCODE" }
}

try {
    Write-Host ''
    Write-Host '=== Chatterbox Voice Studio: setting up components ===' -ForegroundColor Cyan
    Write-Host 'This downloads about 3-5 GB the first time. Please keep this window open.'
    Write-Host ''

    $gpus = (Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }) -join ', '
    $hasNvidia = $gpus -match 'NVIDIA'
    $flavor = if ($hasNvidia) { 'cu126' } else { 'cpu' }
    Write-Host "Graphics: $gpus"
    Write-Host ("PyTorch build: " + $(if ($hasNvidia) { 'NVIDIA GPU (CUDA)' } else { 'CPU only' }))

    $stampValue = "v3|py$PythonVersion|torch$TorchVersion|$flavor|$ChatterboxCommit|$PerthCommit"
    if ((Test-Path $Stamp) -and ((Get-Content $Stamp -Raw).Trim() -eq $stampValue) -and (Test-Path (Join-Path $Venv 'Scripts\pythonw.exe'))) {
        Write-Host 'Components are already installed and up to date.' -ForegroundColor Green
        return
    }

    # 1. uv: a single-file tool that fetches Python and installs packages quickly
    $uv = Join-Path $Runtime 'uv.exe'
    if (-not (Test-Path $uv)) {
        Write-Host '[1/5] Downloading uv (package installer)...'
        $zip = Join-Path $env:TEMP 'uv-windows.zip'
        Invoke-WebRequest -UseBasicParsing 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' -OutFile $zip
        $tmp = Join-Path $env:TEMP 'uv-extract'
        if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        Copy-Item (Get-ChildItem $tmp -Recurse -Filter uv.exe | Select-Object -First 1).FullName $uv
        Remove-Item $zip, $tmp -Recurse -Force
    }
    $env:UV_CACHE_DIR = Join-Path $Runtime 'uv-cache'
    $env:UV_LINK_MODE = 'copy'

    # 2. private Python + virtual environment
    Write-Host "[2/5] Creating a private Python $PythonVersion environment..."
    $pyHome = Join-Path $Runtime 'python'
    if (-not (Test-Path (Join-Path $pyHome 'python.exe'))) {
        if (Test-Path $pyHome) { Remove-Item -Recurse -Force $pyHome }
        $tgz = Join-Path $env:TEMP 'cpython-standalone.tar.gz'
        Invoke-WebRequest -UseBasicParsing $PythonUrl -OutFile $tgz
        Invoke-Native (Join-Path $env:SystemRoot 'System32\tar.exe') @('-xzf', $tgz, '-C', $Runtime)   # extracts to runtime\python
        Remove-Item $tgz -Force
    }
    if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv }
    Invoke-Native $uv @('venv', '--python', (Join-Path $pyHome 'python.exe'), '--no-python-downloads', $Venv)
    $py = Join-Path $Venv 'Scripts\python.exe'

    # 3. PyTorch (CUDA build for NVIDIA GPUs, CPU build otherwise)
    Write-Host "[3/5] Downloading PyTorch $TorchVersion ($flavor) - this is the big one..."
    Invoke-Native $uv @('pip', 'install', '--python', $py, '--index-strategy', 'unsafe-best-match',
        '--index-url', "https://download.pytorch.org/whl/$flavor", '--extra-index-url', 'https://pypi.org/simple',
        "torch==$TorchVersion", "torchaudio==$TorchVersion")

    # 4. Everything else. These mirror Chatterbox's own dependency list, minus gradio (not needed here)
    #    and with the Perth watermarker taken from a pinned GitHub zip (the PyPI release is outdated and
    #    broken without pkg_resources), so that git is not required on this PC.
    Write-Host '[4/5] Installing the other libraries...'
    Invoke-Native $uv @('pip', 'install', '--python', $py,
        'numpy>=1.24.0,<2.0.0', 'librosa==0.11.0', 's3tokenizer', 'transformers==5.2.0', 'diffusers==0.29.0',
        "resemble-perth @ https://github.com/resemble-ai/Perth/archive/$PerthCommit.zip", 'conformer==0.3.2', 'safetensors==0.5.3', 'spacy-pkuseg', 'pykakasi==2.3.0',
        'pyloudnorm', 'omegaconf', 'soundfile', 'PySide6')

    Write-Host '[5/5] Installing Chatterbox...'
    Invoke-Native $uv @('pip', 'install', '--python', $py, '--no-deps',
        "https://github.com/resemble-ai/chatterbox/archive/$ChatterboxCommit.zip")

    Write-Host 'Verifying the installation...'
    $check = Join-Path $Runtime 'verify.py'
    Set-Content -Path $check -Value @(
        'import torch, PySide6, soundfile',
        'from chatterbox.tts_turbo import ChatterboxTurboTTS',
        'from chatterbox.mtl_tts import ChatterboxMultilingualTTS',
        'import perth',
        'assert perth.PerthImplicitWatermarker is not None, "Perth watermarker failed to load"',
        'print("OK - CUDA available:", torch.cuda.is_available())'
    )
    Invoke-Native $py @($check)
    Remove-Item $check -Force

    Set-Content -Path $Stamp -Value $stampValue
    if (Test-Path $env:UV_CACHE_DIR) { Remove-Item -Recurse -Force $env:UV_CACHE_DIR }
    Write-Host ''
    Write-Host 'All components installed.' -ForegroundColor Green
}
catch {
    Write-Host ''
    Write-Host "SETUP FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Details are in $(Join-Path $AppDir 'install.log')."
    if ($PauseOnError) { Read-Host 'Press Enter to close' }
    Stop-Transcript | Out-Null
    exit 1
}
Stop-Transcript | Out-Null
exit 0
