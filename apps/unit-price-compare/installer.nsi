
; Slingshot Tool installer - built by Slingshot Tools
Unicode true
!define APPNAME "Unit Price Compare"
!define SLUG "unit-price-compare"
!define VENDOR "Slingshot Tools"
!define PUBLISHER_URL "https://https://tbougnar.github.io/Slingshot-Tools"
Name "Slingshot Tool - {APPNAME}"
OutFile "/home/runner/work/Slingshot-Tools/Slingshot-Tools/dist/SlingshotTool-unit-price-compare-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\Slingshot Tools\{SLUG}"
InstallDirRegKey HKCU "Software\Slingshot Tools\{SLUG}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Unicode true

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/unit-price-compare/icon.ico"
!define MUI_UNICON "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/unit-price-compare/icon.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\Launch.cmd"
!define MUI_FINISHPAGE_RUN_TEXT "Open {APPNAME} now"

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Install" SecMain
  SetOutPath "$INSTDIR\app"
  File /r "app\*.*"
  SetOutPath "$INSTDIR"
  File "Launch.cmd"

  WriteRegStr HKCU "Software\Slingshot Tools\{SLUG}" "InstallDir" "$INSTDIR"

  ; Start Menu + Desktop shortcuts launch the app in a chromeless app window
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}" "DisplayName" "Slingshot Tool - {APPNAME}"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}" "Publisher" "$VENDOR"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}" "DisplayVersion" "1.0.0"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}" "DisplayIcon" "$INSTDIR\app\icon.png"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}" "NoRepair" 1

  CreateDirectory "$SMPROGRAMS\Slingshot Tools"
  CreateShortcut "$SMPROGRAMS\Slingshot Tools\{APPNAME}.lnk" "$INSTDIR\Launch.cmd"
  CreateShortcut "$SMPROGRAMS\Slingshot Tools\Uninstall {APPNAME}.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\{APPNAME}.lnk" "$INSTDIR\Launch.cmd"

  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR\app"
  Delete "$INSTDIR\Launch.cmd"
  RMDir "$INSTDIR"
  Delete "$DESKTOP\{APPNAME}.lnk"
  RMDir "$SMPROGRAMS\Slingshot Tools"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{SLUG}"
  DeleteRegKey HKCU "Software\Slingshot Tools\{SLUG}"
SectionEnd
