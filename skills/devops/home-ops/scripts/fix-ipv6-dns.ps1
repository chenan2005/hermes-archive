<![CDATA[# Fix Windows IPv6 DNS pollution for home network behind OpenClash
# 
# Problem: Windows on 71.x subnet gets telecom IPv6 DNS from OLT's RA RDNSS.
#   These DNS servers return poisoned results for foreign domains.
#   Even though IPv4 DNS (192.168.71.9 -> OpenClash) is correct, Windows
#   may prefer IPv6 DNS.
#
# Solution: Set DisabledComponents=0x20 (prefer IPv4 over IPv6 for DNS).
#   - All DNS queries prefer IPv4 (router -> OpenClash)
#   - IPv6 SLAAC addresses still work
#   - Domestic IPv6 connectivity unaffected
#   - Survives reboots and DHCP/RA renewals
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File fix-ipv6-dns.ps1
#   powershell -ExecutionPolicy Bypass -File fix-ipv6-dns.ps1 -Apply  # actually apply
#
# Deploy:
#   Copy to target machine and run as Administrator

param(
    [switch]$Apply = $false
)

$IPv4_DNS = @("192.168.71.9")  # ImmortalWrt router
$DISABLED_COMPONENTS = 0x20

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " IPv6 DNS Fix for OpenClash Home Network" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Find active ethernet adapters (exclude virtual, WiFi, Bluetooth)
$activeAdapters = Get-NetAdapter | Where-Object {
    $_.Status -eq 'Up' -and
    $_.InterfaceDescription -match 'Ethernet|Realtek|Intel|PCIe' -and
    $_.InterfaceDescription -notmatch 'Bluetooth|VNIC|Tunnel|Virtual'
}

if (-not $activeAdapters) {
    Write-Host "[ERROR] No active Ethernet adapter found." -ForegroundColor Red
    Write-Host "Available adapters:"
    Get-NetAdapter | Format-Table Name, Status, InterfaceDescription
    exit 1
}

Write-Host "[INFO] Active Ethernet adapter(s):" -ForegroundColor Yellow
$activeAdapters | ForEach-Object {
    Write-Host "  - $($_.Name) ($($_.InterfaceDescription))"
}
Write-Host ""

# --- Current State ---
Write-Host "--- Current State ---" -ForegroundColor Gray

foreach ($adapter in $activeAdapters) {
    $name = $adapter.Name
    Write-Host ""
    Write-Host "Adapter: $name" -ForegroundColor White

    # IPv4 DNS
    $v4dns = Get-DnsClientServerAddress -InterfaceAlias $name -AddressFamily IPv4 -ErrorAction SilentlyContinue
    if ($v4dns -and $v4dns.ServerAddresses.Count -gt 0) {
        Write-Host "  IPv4 DNS: $($v4dns.ServerAddresses -join ', ')" -ForegroundColor Green
    } else {
        Write-Host "  IPv4 DNS: (none)" -ForegroundColor Red
    }

    # IPv6 DNS
    $v6dns = Get-DnsClientServerAddress -InterfaceAlias $name -AddressFamily IPv6 -ErrorAction SilentlyContinue
    if ($v6dns -and $v6dns.ServerAddresses.Count -gt 0) {
        Write-Host "  IPv6 DNS: $($v6dns.ServerAddresses -join ', ')" -ForegroundColor Yellow
    } else {
        Write-Host "  IPv6 DNS: (none)" -ForegroundColor Green
    }
}

# DisabledComponents registry key
try {
    $dc = Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters' -Name 'DisabledComponents' -ErrorAction Stop
    Write-Host ""
    Write-Host "DisabledComponents = 0x$($dc.DisabledComponents.ToString('X'))" -ForegroundColor $(if ($dc.DisabledComponents -eq 0x20) { 'Green' } else { 'Yellow' })
} catch {
    Write-Host ""
    Write-Host "DisabledComponents: (not set, default 0x0)" -ForegroundColor Yellow
}

# --- Apply Fix ---
if (-not $Apply) {
    Write-Host ""
    Write-Host "DRY RUN. To apply, run with -Apply switch." -ForegroundColor Magenta
    Write-Host "  powershell -ExecutionPolicy Bypass -File fix-ipv6-dns.ps1 -Apply"
    exit 0
}

Write-Host ""
Write-Host "--- Applying Fix ---" -ForegroundColor Cyan

# 1. Set DisabledComponents=0x20
Write-Host "[1/3] Setting DisabledComponents = 0x20 ..."
$regPath = 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters'
try {
    Set-ItemProperty -Path $regPath -Name 'DisabledComponents' -Value $DISABLED_COMPONENTS -Type DWORD -Force
    Write-Host "  OK: DisabledComponents = 0x$($DISABLED_COMPONENTS.ToString('X'))" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Failed to set registry key: $_" -ForegroundColor Red
    exit 1
}

# 2. Ensure IPv4 DNS points to router
Write-Host "[2/3] Ensuring IPv4 DNS = $($IPv4_DNS -join ', ') ..."
foreach ($adapter in $activeAdapters) {
    $name = $adapter.Name
    try {
        Set-DnsClientServerAddress -InterfaceAlias $name -ServerAddresses $IPv4_DNS
        Write-Host "  OK: $name IPv4 DNS set" -ForegroundColor Green
    } catch {
        Write-Host "  WARN: $name IPv4 DNS: $_" -ForegroundColor Yellow
    }
}

# 3. Restart DNS client service to pick up changes
Write-Host "[3/3] Restarting DNS Client service ..."
try {
    Restart-Service -Name Dnscache -Force -ErrorAction SilentlyContinue
    Write-Host "  OK: DNS Client restarted" -ForegroundColor Green
} catch {
    Write-Host "  INFO: DNS Client restart skipped (may need reboot)." -ForegroundColor Yellow
    Write-Host "        Changes will take effect automatically."
}

# --- Verify ---
Write-Host ""
Write-Host "--- Verification ---" -ForegroundColor Cyan

$dc = Get-ItemProperty -Path $regPath -Name 'DisabledComponents'
Write-Host "DisabledComponents = 0x$($dc.DisabledComponents.ToString('X'))" -ForegroundColor Green

foreach ($adapter in $activeAdapters) {
    $name = $adapter.Name
    $v4 = (Get-DnsClientServerAddress -InterfaceAlias $name -AddressFamily IPv4).ServerAddresses -join ', '
    Write-Host "$name IPv4 DNS: $v4" -ForegroundColor Green
}

Write-Host ""
Write-Host "Done. DNS queries now prefer IPv4 (router -> OpenClash)." -ForegroundColor Green
Write-Host "IPv6 connectivity preserved for domestic sites." -ForegroundColor Green
]]>