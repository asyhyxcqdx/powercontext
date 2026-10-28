# Creates ONE real seekdb D0 instance and writes its credentials only to local .env.
# DO NOT share .env or commit it to Git.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (Test-Path -LiteralPath '.env') {
    throw '.env already exists. This script refuses to overwrite your existing database credentials.'
}
Write-Host 'Creating a new seekdb D0 instance (7-day disposable trial)...'
$result = Invoke-RestMethod -Method Post -Uri 'https://d0.seekdb.ai/api/v1/instances' -TimeoutSec 40
$required = @('instance_id', 'host', 'port', 'username', 'password', 'database')
foreach ($field in $required) {
    if ($null -eq $result.$field -or [string]::IsNullOrWhiteSpace([string]$result.$field)) {
        throw "D0 response missing field: $field (no .env was created)."
    }
}
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
$accessKey = -join ($bytes | ForEach-Object { $_.ToString('x2') })
$envLines = @(
    "D0_INSTANCE_ID=$($result.instance_id)"
    "D0_EXPIRES_AT=$($result.expires_at)"
    "SEEKDB_HOST=$($result.host)"
    "SEEKDB_PORT=$($result.port)"
    "SEEKDB_USERNAME=$($result.username)"
    "SEEKDB_PASSWORD=$($result.password)"
    "SEEKDB_DATABASE=$($result.database)"
    'SEEKDB_REQUIRE_TLS=true'
    "COURT_API_KEY=$accessKey"
)
$body = ($envLines -join "`n") + "`n"
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot '.env'), $body, (New-Object System.Text.UTF8Encoding($false)))
Write-Host 'D0_CREATED: .env saved locally. Password and API key were NOT printed.'
if ($result.PSObject.Properties.Name -contains 'instance_id') {
    Write-Host "Instance ID: $($result.instance_id)"
}
Write-Host 'Important: this database automatically expires after 7 days.'
