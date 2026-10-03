
; Slingshot Tool installer - built by Slingshot Tools
Unicode true
!define APPNAME "Compound Interest"
!define BRAND "Slingshot Tools"
!define SLUG "compound-interest"
!define VENDOR "Slingshot Tools"
!define PUBLISHER_URL "https://https://tbougnar.github.io/Slingshot-Tools"
Name "Compound Interest"
OutFile "/home/runner/work/Slingshot-Tools/Slingshot-Tools/dist/SlingshotTool-compound-interest-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\Slingshot Tools\compound-interest"
InstallDirRegKey HKCU "Software\Slingshot Tools\compound-interest" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Unicode true

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/compound-interest/icon.ico"
!define MUI_UNICON "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/compound-interest/icon.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\Start App.cmd"
!define MUI_FINISHPAGE_RUN_TEXT "Start Compound Interest"

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Install" SecMain
  SetOutPath "$INSTDIR\app"
  File /r "app\*.*"
  SetOutPath "$INSTDIR"
  File "launcher.py"
  File "app\app.json"
  File "Start App.cmd"

  WriteRegStr HKCU "Software\Slingshot Tools\compound-interest" "InstallDir" "$INSTDIR"

  ; Start Menu + Desktop shortcuts launch the app in a chromeless app window
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\compound-interest" "DisplayName" "Compound Interest"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\compound-interest" "Publisher" "$VENDOR"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\compound-interest" "DisplayVersion" "1.0.0"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\compound-interest" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\compound-interest" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\compound-interest" "DisplayIcon" "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/compound-interest/icon.ico"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\compound-interest" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\compound-interest" "NoRepair" 1

  CreateShortcut "$SMPROGRAMS\Compound Interest.lnk" "$INSTDIR\Start App.cmd" "" "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/compound-interest/icon.ico" 0
  CreateShortcut "$SMPROGRAMS\Uninstall Compound Interest.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\Compound Interest.lnk" "$INSTDIR\Start App.cmd" "" "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/compound-interest/icon.ico" 0

  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR\app"
  Delete "$INSTDIR\Start App.cmd"
  Delete "$INSTDIR\launcher.py"
  Delete "$INSTDIR\app\app.json"
  RMDir "$INSTDIR"
  Delete "$DESKTOP\Compound Interest.lnk"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\compound-interest"
  DeleteRegKey HKCU "Software\Slingshot Tools\compound-interest"
SectionEnd
