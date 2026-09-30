param(
    [Parameter(Mandatory)][string]$SecretEnvFile,
    [string]$Namespace = 'gaik',
    [switch]$EnableWizard
)
$ErrorActionPreference = 'Stop'
if (-not (Get-Command oc -ErrorAction SilentlyContinue)) { throw 'oc is required.' }
$secretFile = (Resolve-Path -LiteralPath $SecretEnvFile).Path
$checkout = (& git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Run this script from a Git checkout.' }
$privatePath = [IO.Path]::GetFullPath($secretFile)
$repoPath = [IO.Path]::GetFullPath($checkout) + [IO.Path]::DirectorySeparatorChar
if ($privatePath.StartsWith($repoPath, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Keep real secret env files outside the public checkout.'
}
$settings = @{}
foreach ($line in Get-Content -LiteralPath $secretFile) {
    if ($line -match '^([A-Z][A-Z0-9_]*)=(.*)$') {
        $settings[$Matches[1]] = $Matches[2]
    }
}
$expected = Get-Content (Join-Path $PSScriptRoot 'secrets.env.example') |
    Where-Object { $_ -match '^[A-Z][A-Z0-9_]*=' } |
    ForEach-Object { ($_ -split '=', 2)[0] }
foreach ($key in $expected) {
    if (-not $settings[$key] -or $settings[$key] -match 'CHANGE_ME') {
        throw "Missing or placeholder setting: $key"
    }
}
if ($settings.ENCRYPTION_KEY -notmatch '^[a-fA-F0-9]{64}$') {
    throw 'ENCRYPTION_KEY must be 64 hexadecimal characters.'
}

function Set-PrivateSecret([string]$Name, [hashtable]$Data) {
    $payload = @{
        apiVersion = 'v1'; kind = 'Secret'; type = 'Opaque'
        metadata = @{ name = $Name; namespace = $Namespace }
        stringData = $Data
    } | ConvertTo-Json -Depth 6 -Compress
    # Do not persist credentials in kubectl's last-applied annotation.
    $existing = & oc -n $Namespace get secret $Name --ignore-not-found -o name 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect runtime secret.' }
    if ($existing) {
        $resource = $payload | ConvertFrom-Json
        $version = & oc -n $Namespace get secret $Name -o 'jsonpath={.metadata.resourceVersion}'
        if ($LASTEXITCODE -ne 0) { throw 'Cannot read secret version.' }
        $resource.metadata | Add-Member resourceVersion $version
        $payload = $resource | ConvertTo-Json -Depth 6 -Compress
        $result = $payload | & oc replace -f - 2>&1
    } else {
        $result = $payload | & oc create -f - 2>&1
    }
    if ($LASTEXITCODE -ne 0) { throw "Cannot save secret $Name; inspect oc access privately." }
    Write-Host "Runtime secret $Name ready."
}

Set-PrivateSecret 'langfuse-pilot' $settings
& oc -n $Namespace apply -f (Join-Path $PSScriptRoot 'pilot.yaml')
if ($LASTEXITCODE -ne 0) { throw 'Langfuse resource apply failed.' }
foreach ($name in 'langfuse-pilot-data', 'langfuse-pilot-web', 'langfuse-pilot-worker') {
    & oc -n $Namespace rollout status "deployment/$name" --timeout=60s
    if ($LASTEXITCODE -ne 0) { throw "Deployment $name is not ready; inspect pods before continuing." }
}
if ($EnableWizard) {
    Set-PrivateSecret 'gaik-demo-langfuse' @{
        WIZARD_LANGFUSE_ENABLED = 'true'
        LANGFUSE_BASE_URL = 'http://langfuse-pilot:3000'
        LANGFUSE_PUBLIC_KEY = $settings.LANGFUSE_INIT_PROJECT_PUBLIC_KEY
        LANGFUSE_SECRET_KEY = $settings.LANGFUSE_INIT_PROJECT_SECRET_KEY
    }
    $result = & oc -n $Namespace set env deployment/gaik-demo-api --from=secret/gaik-demo-langfuse 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Cannot enable wizard diagnostics; inspect deployment access.' }
    & oc -n $Namespace rollout status deployment/gaik-demo-api --timeout=60s
    if ($LASTEXITCODE -ne 0) { throw 'Demo API rollout is not ready.' }
}
