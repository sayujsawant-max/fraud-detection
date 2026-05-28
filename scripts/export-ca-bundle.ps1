# =============================================================================
# Export the Windows trusted-root certificate store to a PEM bundle that the
# Docker build containers can install. Needed on machines that sit behind a
# TLS-intercepting proxy (Zscaler, Cisco Umbrella, corporate firewall) where
# the proxy re-signs HTTPS connections with a private root CA.
#
# Drops two copies — one for the backend build context and one for the
# frontend — at the paths each Dockerfile expects.
#
# Re-run this script whenever the corporate CA rotates or you move machines.
# =============================================================================

$ErrorActionPreference = "Stop"

$repoRoot   = Split-Path -Parent $PSScriptRoot
$targets    = @(
    (Join-Path $repoRoot "backend\certs\ca-bundle.pem"),
    (Join-Path $repoRoot "frontend\certs\ca-bundle.pem")
)

$stores = @(
    "Cert:\LocalMachine\Root",
    "Cert:\CurrentUser\Root",
    "Cert:\LocalMachine\CA",
    "Cert:\CurrentUser\CA"
)

$certs = @()
foreach ($store in $stores) {
    $certs += Get-ChildItem -Path $store -ErrorAction SilentlyContinue
}

$seen  = @{}
$lines = New-Object System.Collections.Generic.List[string]
foreach ($c in $certs) {
    if (-not $c -or $seen.ContainsKey($c.Thumbprint)) { continue }
    $seen[$c.Thumbprint] = $true
    $b64 = [Convert]::ToBase64String($c.RawData, [System.Base64FormattingOptions]::InsertLineBreaks)
    $lines.Add("# Subject: $($c.Subject)")
    $lines.Add("# Issuer:  $($c.Issuer)")
    $lines.Add("# Thumbprint: $($c.Thumbprint)")
    $lines.Add("-----BEGIN CERTIFICATE-----")
    $lines.Add($b64)
    $lines.Add("-----END CERTIFICATE-----")
    $lines.Add("")
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
foreach ($t in $targets) {
    $dir = Split-Path -Parent $t
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    [IO.File]::WriteAllLines($t, $lines, $utf8NoBom)
    Write-Host "Wrote $($seen.Count) certs to $t"
}
