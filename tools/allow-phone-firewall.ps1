# One-time setup for the phone remote: lets devices on your home network reach it.
# Run from an admin PowerShell:  powershell -ExecutionPolicy Bypass -File tools\allow-phone-firewall.ps1 [-Port 8771]
#
# The rule only accepts connections from your local subnet (devices on the same WiFi),
# so the port stays closed to everything else even on public networks.
param([int]$Port = 8771)

New-NetFirewallRule `
    -DisplayName "Knob Mixer phone remote (port $Port)" `
    -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort $Port `
    -RemoteAddress LocalSubnet `
    -Profile Any
