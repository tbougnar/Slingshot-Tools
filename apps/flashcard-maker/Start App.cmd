@echo off
cd /d "%~dp0"
where pythonw >nul 2>&1 && (start "" pythonw launcher.py & exit /b 0)
where python  >nul 2>&1 && (start "" python  launcher.py & exit /b 0)
rem Slingshot Tool launcher - opens the app in a real native window
set "APPDIR=%~dp0app\index.html"
set "FILEURL=file:///%APPDIR:\=\%"
if exist "%ProgramFiles(x86)%\Microsoft%\Edge%\Application%\msedge.exe" (
  start "" "%ProgramFiles(x86)%\Microsoft%\Edge%\Application%\msedge.exe" --app="%FILEURL%" --window-size=1180,820
  exit /b 0
)
if exist "%ProgramFiles%\Microsoft%\Edge%\Application%\msedge.exe" (
  start "" "%ProgramFiles%\Microsoft%\Edge%\Application%\msedge.exe" --app="%FILEURL%" --window-size=1180,820
  exit /b 0
)
start "" "%FILEURL%"
