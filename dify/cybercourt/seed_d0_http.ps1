# Initialize 36 REAL seekdb records using official D0 HTTPS SQL API.
# Does not require Python, MySQL client, or public network tunnel.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (!(Test-Path -LiteralPath '.env')) { throw 'Missing .env; run create_d0.ps1 first.' }

$kv = @{}
Get-Content -LiteralPath '.env' -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^([A-Z0-9_]+)=(.*)$') { $kv[$matches[1]] = $matches[2] }
}
if (!$kv['D0_INSTANCE_ID'] -or !$kv['SEEKDB_PASSWORD']) {
    throw 'D0_INSTANCE_ID or SEEKDB_PASSWORD missing from .env. Only D0 trial supports this script.'
}

function Invoke-D0Sql([string]$sql) {
    $payload = @{ instance_id = $kv['D0_INSTANCE_ID']; password = $kv['SEEKDB_PASSWORD']; sql = $sql } |
        ConvertTo-Json -Depth 6 -Compress
    $response = Invoke-RestMethod -Method Post -Uri 'https://d0.seekdb.ai/api/v1/query' `
        -ContentType 'application/json; charset=utf-8' `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($payload)) -TimeoutSec 60
    if (($response.PSObject.Properties.Name -contains 'success') -and ($response.success -eq $false)) {
        throw 'D0 returned success=false. Check service status and table permissions.'
    }
    if (($response.PSObject.Properties.Name -contains 'error') -and $response.error) {
        throw ('D0 SQL error: ' + $response.error)
    }
    return $response
}
function SqlQuote([string]$s) {
    return "'" + $s.Replace([string][char]92, ([string][char]92 + [string][char]92)).Replace("'", "''") + "'"
}

Write-Host 'Creating seekdb tables over official D0 HTTPS SQL API...'
Invoke-D0Sql @'
CREATE TABLE IF NOT EXISTS cyber_case_catalog (
    case_id VARCHAR(16) NOT NULL PRIMARY KEY,
    category VARCHAR(24) NOT NULL,
    title VARCHAR(160) NOT NULL,
    summary TEXT NOT NULL,
    tags VARCHAR(255) NOT NULL,
    verdict TEXT NOT NULL,
    twist TEXT NOT NULL,
    INDEX idx_category (category)
) DEFAULT CHARSET=utf8mb4
'@ | Out-Null
Invoke-D0Sql @'
CREATE TABLE IF NOT EXISTS cyber_case_plays (
    play_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    case_id VARCHAR(16) NOT NULL,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_play_case (case_id)
) DEFAULT CHARSET=utf8mb4
'@ | Out-Null

$cases = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'cases.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$columns = @('case_id', 'category', 'title', 'summary', 'tags', 'verdict', 'twist')
$inserted = 0
for ($i = 0; $i -lt $cases.Count; $i += 6) {
    $last = [Math]::Min($i + 5, $cases.Count - 1)
    $tuples = @()
    foreach ($case in $cases[$i..$last]) {
        $vals = @(foreach ($field in $columns) { SqlQuote ([string]$case.PSObject.Properties[$field].Value) })
        $tuples += '(' + ($vals -join ',') + ')'
    }
    $sql = 'INSERT INTO cyber_case_catalog (case_id,category,title,summary,tags,verdict,twist) VALUES ' +
        ($tuples -join ',') +
        ' ON DUPLICATE KEY UPDATE category=VALUES(category), title=VALUES(title), summary=VALUES(summary), tags=VALUES(tags), verdict=VALUES(verdict), twist=VALUES(twist)'
    Invoke-D0Sql $sql | Out-Null
    $inserted += $tuples.Count
    Write-Host ("Seed progress: $inserted / $($cases.Count)")
}
Write-Host 'Checking actual SELECT query result from seekdb...'
$check = Invoke-D0Sql 'SELECT COUNT(*) AS total_cases FROM cyber_case_catalog'
$check | ConvertTo-Json -Depth 8
Write-Host 'SEEKDB_D0_HTTP_SEED_REQUESTS_COMPLETED. Verify total_cases = 36 in the response.'
Write-Host 'DO NOT upload .env or share D0 secrets.'
