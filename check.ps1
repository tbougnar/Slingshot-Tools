# Verify every connection the weekly cycle needs.
#
# Credentials live in GitHub Actions secrets, so the check runs there. Run it
# from the Actions tab after changing anything, or run this file here on your
# own machine, where it can reach services that block cloud runners.
#
# On your machine, set the values first in the SAME window:
#   $env:GROQ_API_KEY="gsk_..."
#   $env:DISCORD_BOT_TOKEN="..."
#   $env:DISCORD_GUILD_ID="1516907450983383201"
#   $env:ITCH_USER="slingshot-tools"
#   $env:ITCH_API_KEY="..."
#   $env:ITCH_SESSION_COOKIE="itchio_token=..."
#   .\check.ps1
#
# Where each value comes from:
#   GROQ_API_KEY          https://console.groq.com/keys
#   DISCORD_BOT_TOKEN     Developer Portal, your app, Bot, Reset Token
#   DISCORD_GUILD_ID      right-click the server name, Copy Server ID
#   ITCH_USER             your itch.io subdomain, lowercase
#   ITCH_API_KEY          https://itch.io/settings/user, Developer API Keys
#   ITCH_SESSION_COOKIE   itch.io, F12, Console, document.cookie,
#                         the itchio_token= part only

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$missing = @()
foreach ($name in "GROQ_API_KEY", "DISCORD_BOT_TOKEN", "ITCH_USER",
                "ITCH_API_KEY", "ITCH_SESSION_COOKIE") {
    if (-not (Test-Path "env:$name") -or -not $env:$name) {
        $missing += $name
    }
}

if ($missing.Count) {
    Write-Host ""
    Write-Host "  Missing: $($missing -join ', ')" -ForegroundColor Yellow
    Write-Host "  See the list of sources at the top of this file." -ForegroundColor Yellow
    Write-Host ""
}

python check_connections.py
exit $LASTEXITCODE