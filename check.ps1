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
#   YOUTUBE_*             https://console.cloud.google.com/apis/credentials
#   DISCORD_WEBHOOK_URL   server settings, Integrations, Webhooks

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# Every variable check_connections.py actually reads. This list was short by
# five, including DISCORD_GUILD_ID, which is named in the comment block above
# but was not checked: a missing guild id was only discovered after the check
# had already run and reported on everything else.
$required = "GROQ_API_KEY", "DISCORD_BOT_TOKEN", "DISCORD_GUILD_ID",
            "ITCH_USER", "ITCH_API_KEY", "ITCH_SESSION_COOKIE"

$missing = @()
foreach ($name in $required) {
    # "env:$name" does not expand: PowerShell reads the whole thing as a
    # variable name and fails to parse the line. ${name} is the correct form,
    # and the original had the same fault, so this file had never run.
    if (-not [Environment]::GetEnvironmentVariable($name)) {
        $missing += $name
    }
}

# Optional, but the check reports less without them, so they are listed
# separately rather than treated as a failure.
$optional = "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN",
            "DISCORD_WEBHOOK_URL", "YOUTUBE_API_KEY"

$absent = @()
foreach ($name in $optional) {
    if (-not [Environment]::GetEnvironmentVariable($name)) {
        $absent += $name
    }
}

if ($absent.Count) {
    Write-Host ""
    Write-Host "  Not set (the check will report these as unavailable):" -ForegroundColor DarkGray
    Write-Host "    $($absent -join ', ')" -ForegroundColor DarkGray
}

if ($missing.Count) {
    Write-Host ""
    Write-Host "  Missing: $($missing -join ', ')" -ForegroundColor Yellow
    Write-Host "  See the list of sources at the top of this file." -ForegroundColor Yellow
    Write-Host ""
}

python check_connections.py
exit $LASTEXITCODE