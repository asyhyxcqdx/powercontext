# Read-only audit of real seekdb tables through the official D0 HTTPS SQL API.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$kv = @{}
if (!(Test-Path '.env')) { throw '.env not found.' }
Get-Content -LiteralPath '.env' -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^([A-Z0-9_]+)=(.*)$') { $kv[$matches[1]] = $matches[2] }
}
if (!$kv['D0_INSTANCE_ID'] -or !$kv['SEEKDB_PASSWORD']) { throw 'D0 credentials missing from .env' }
function D0Query([string]$sql) {
    $json = @{instance_id=$kv['D0_INSTANCE_ID'];password=$kv['SEEKDB_PASSWORD'];sql=$sql} | ConvertTo-Json -Compress
    $res = Invoke-RestMethod -Uri 'https://d0.seekdb.ai/api/v1/query' -Method Post `
         -ContentType 'application/json; charset=utf-8' `
         -Body ([Text.Encoding]::UTF8.GetBytes($json)) -TimeoutSec 60
    if (($res.PSObject.Properties.Name -contains 'error') -and $res.error) { throw ('D0 error: ' + $res.error) }
    $res | ConvertTo-Json -Depth 10
}
Write-Host 'CASE TABLE COUNT (expected 36):'
D0Query 'SELECT COUNT(*) AS total_cases FROM cyber_case_catalog'
Write-Host 'PLAY LOG COUNT (read-only Dify flow does NOT insert logs; expected 0 on a fresh instance):'
D0Query 'SELECT COUNT(*) AS total_hearings FROM cyber_case_plays'
Write-Host 'TOP 5 CASES (real SQL aggregation):'
D0Query 'SELECT c.case_id, c.title, COUNT(p.play_id) AS plays FROM cyber_case_catalog c LEFT JOIN cyber_case_plays p ON c.case_id = p.case_id GROUP BY c.case_id, c.title ORDER BY plays DESC LIMIT 5'
