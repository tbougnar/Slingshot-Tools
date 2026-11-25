# Put makensis on the runner without depending on the Chocolatey community
# feed. That feed answered 406 and 504 twice in a row while a paid release was
# waiting for its installer, and every later step was skipped because one tool
# could not be fetched. The official NSIS installer is a small, static file, so
# download it directly and verify the executable before saying we succeeded.
param([switch]$WarnOnly)

$ErrorActionPreference = 'Stop'

function Find-Makensis {
    $places = @(
        "$env:ProgramFiles\NSIS\makensis.exe",
        "${env:ProgramFiles(x86)}\NSIS\makensis.exe",
        'C:\NSIS\makensis.exe',
        "$env:LOCALAPPDATA\NSIS\makensis.exe"
    )
    foreach ($place in $places) {
        if ($place -and (Test-Path $place)) { return $place }
    }
    $found = Get-Command makensis.exe -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
    return ''
}

$exe = Find-Makensis
if (-not $exe) {
    $setup = Join-Path $env:TEMP 'nsis-3.11-setup.exe'
    $urls = @(
        'https://downloads.sourceforge.net/project/nsis/NSIS%203/3.11/nsis-3.11-setup.exe',
        'https://sourceforge.net/projects/nsis/files/NSIS%203/3.11/nsis-3.11-setup.exe/download'
    )
    $got = $false
    foreach ($url in $urls) {
        try {
            Write-Output "downloading NSIS from $url"
            & curl.exe -fL --retry 3 --connect-timeout 30 --max-time 300 -o $setup $url
            if (($LASTEXITCODE -eq 0) -and (Test-Path $setup) -and
                ((Get-Item $setup).Length -gt 500000)) {
                $got = $true
                break
            }
        } catch {
            Write-Output "::warning::NSIS download failed from $url"
        }
    }

    if ($got) {
        # /D has to be the last argument and unquoted for NSIS to use it.
        Write-Output 'installing NSIS silently into C:\NSIS'
        $proc = Start-Process -FilePath $setup -ArgumentList '/S', '/D=C:\NSIS' -Wait -PassThru
        if ($proc.ExitCode -ne 0) {
            Write-Output "::warning::NSIS installer exited $($proc.ExitCode)"
        }
    } else {
        Write-Output '::warning::direct download failed; trying Chocolatey'
        choco install nsis -y --no-progress
    }
    $exe = Find-Makensis
}

if (-not $exe) {
    if ($WarnOnly) {
        # The generate job can still stage an app without an installer; the
        # separate Windows job builds it. The publish job must not continue.
        Write-Output '::warning::NSIS is unavailable; no installer can be built here'
        exit 0
    }
    Write-Output '::error::NSIS could not be installed; makensis.exe was not found'
    exit 1
}

Write-Output "makensis at $exe"
Add-Content -Path $env:GITHUB_PATH -Value (Split-Path $exe)
