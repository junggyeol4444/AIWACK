# User-initiated optional first-time download; never bypass PowerShell policy.
$ErrorActionPreference = 'Stop'
$root = Join-Path $PSScriptRoot 'local_models'
New-Item -ItemType Directory -Force -Path $root | Out-Null

$engineZip = Join-Path $root 'llama-b11433-bin-win-cpu-x64.zip'
$engineUri = 'https://github.com/ggml-org/llama.cpp/releases/download/b11433/llama-b11433-bin-win-cpu-x64.zip'
$engineSha = '301943380e45deae3991d42dddd03fae65c6a4963a5d882328a60208b43aa9e0'
$gguf = Join-Path $root 'SmolLM2-135M-Instruct-Q4_K_M.gguf'
$ggufUri = 'https://huggingface.co/lmstudio-community/SmolLM2-135M-Instruct-GGUF/resolve/main/SmolLM2-135M-Instruct-Q4_K_M.gguf?download=true'
$ggufSha = 'bda484992f9655d22504b14e57985257fa6a86937c61f957cf99c10a3bcae169'

if (!(Test-Path $engineZip)) {
    Write-Host 'Downloading officially released llama.cpp CPU runner...'
    Invoke-WebRequest -Uri $engineUri -OutFile $engineZip -MaximumRedirection 10
}
if ((Get-FileHash $engineZip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $engineSha) {
    throw 'llama.cpp SHA256 mismatch. Stop: refuse untrusted executable.'
}
$binRoot = Join-Path $root 'llama_cpu'
if (!(Test-Path $binRoot)) {
    Expand-Archive -LiteralPath $engineZip -DestinationPath $binRoot
}
$cli = Get-ChildItem $binRoot -Recurse -File -Filter 'llama-completion.exe' | Select-Object -First 1
if (!$cli) { throw 'Official archive does not include llama-completion.exe' }

if (!(Test-Path $gguf)) {
    Write-Host 'Downloading genuine GGUF model...'
    Invoke-WebRequest -Uri $ggufUri -OutFile $gguf -MaximumRedirection 10
}
if ((Get-FileHash $gguf -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ggufSha) {
    throw 'GGUF SHA256 mismatch. Stop: refuse untrusted model.'
}
if ((Get-Item $gguf).Length -lt 80000000 -or (Get-Item $gguf).Length -gt 120000000) {
    throw 'GGUF model size unexpected'
}
$stream = [System.IO.File]::OpenRead($gguf)
try {
    $magic = [byte[]]::new(4)
    [void]$stream.Read($magic,0,4)
    if ([System.Text.Encoding]::ASCII.GetString($magic) -ne 'GGUF') { throw 'Invalid GGUF header' }
} finally { $stream.Dispose() }
Write-Host 'SHA256 verified. Open AIWACK.exe > Local AI Model Connection:'
Write-Host "llama-completion.exe: $($cli.FullName)"
Write-Host "GGUF model: $gguf"
Write-Host 'The model is not connected until you explicitly configure it inside AIWACK.exe.'
