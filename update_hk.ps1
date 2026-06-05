# HK Stock Database Updater
# Run this on your local machine: powershell -File update_hk.ps1
$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $scriptDir) { $scriptDir = Get-Location }

Write-Host "Fetching HK stock list from Eastmoney..." -ForegroundColor Cyan

$headers = @{
    "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    "Referer" = "https://data.eastmoney.com/"
}

$stocks = @{}
$page = 1
$totalPages = $null

while ($true) {
    $url = "https://push2.eastmoney.com/api/qt/clist/get?pn=$page&pz=500&po=1&np=1&fltt=2&invt=2&fid=f12&fs=m:128+t:3,m:128+t:4,m:128+t:1,m:128+t:2&fields=f12,f14"
    try {
        $resp = Invoke-RestMethod -Uri $url -Headers $headers -TimeoutSec 20
        $items = $resp.data.diff
        if (-not $items -or $items.Count -eq 0) { break }

        foreach ($item in $items) {
            $code = $item.f12
            $name = $item.f14
            if ($code -and $name) {
                $stocks[$code.PadLeft(5, '0')] = $name
            }
        }

        $serverTotal = $resp.data.total
        Write-Host "  Page $page : $($items.Count) stocks (collected: $($stocks.Count), total: $serverTotal)" -ForegroundColor Gray

        if ($items.Count -lt 500) { break }
        $page++
    } catch {
        Write-Host "  Error on page $page : $_" -ForegroundColor Red
        break
    }
}

if ($stocks.Count -eq 0) {
    Write-Host "FAILED: No stocks fetched!" -ForegroundColor Red
    exit 1
}

# Generate Python file
$outputPath = Join-Path $scriptDir "hk_stock_names.py"
$sorted = $stocks.GetEnumerator() | Sort-Object Key

$sb = [System.Text.StringBuilder]::new()
[void]$sb.AppendLine("# Auto-generated HK stock database")
[void]$sb.AppendLine("# Updated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
[void]$sb.AppendLine("# Total: $($stocks.Count)")
[void]$sb.AppendLine("HK_STOCK_NAMES = {")

foreach ($entry in $sorted) {
    $safeName = $entry.Value -replace '"', '\"' -replace "'", "\'"
    [void]$sb.AppendLine('    "' + $entry.Key + '": "' + $safeName + '",')
}
[void]$sb.AppendLine("}")

[System.IO.File]::WriteAllText($outputPath, $sb.ToString(), [System.Text.UTF8Encoding]::new($false))
Write-Host ""
Write-Host "Done! $($stocks.Count) HK stocks written to $outputPath" -ForegroundColor Green
Write-Host "Now commit and push: git add hk_stock_names.py && git commit -m 'update hk stocks' && git push" -ForegroundColor Yellow
