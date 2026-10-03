
; Slingshot Tool installer - built by Slingshot Tools
Unicode true
!define APPNAME "Tax & Tip Calculator"
!define BRAND "Slingshot Tools"
!define SLUG "gst-calculator"
!define VENDOR "Slingshot Tools"
!define PUBLISHER_URL "https://https://tbougnar.github.io/Slingshot-Tools"
Name "Tax & Tip Calculator"
OutFile "/home/runner/work/Slingshot-Tools/Slingshot-Tools/dist/SlingshotTool-gst-calculator-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\Slingshot Tools\gst-calculator"
InstallDirRegKey HKCU "Software\Slingshot Tools\gst-calculator" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Unicode true

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/gst-calculator/icon.ico"
!define MUI_UNICON "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/gst-calculator/icon.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\Start App.cmd"
!define MUI_FINISHPAGE_RUN_TEXT "Start Tax & Tip Calculator"

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

  WriteRegStr HKCU "Software\Slingshot Tools\gst-calculator" "InstallDir" "$INSTDIR"

  ; Start Menu + Desktop shortcuts launch the app in a chromeless app window
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\gst-calculator" "DisplayName" "Tax & Tip Calculator"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\gst-calculator" "Publisher" "$VENDOR"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\gst-calculator" "DisplayVersion" "1.0.0"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\gst-calculator" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\gst-calculator" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\gst-calculator" "DisplayIcon" "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/gst-calculator/icon.ico"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\gst-calculator" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\gst-calculator" "NoRepair" 1

  CreateShortcut "$SMPROGRAMS\Tax & Tip Calculator.lnk" "$INSTDIR\Start App.cmd" "" "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/gst-calculator/icon.ico" 0
  CreateShortcut "$SMPROGRAMS\Uninstall Tax & Tip Calculator.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\Tax & Tip Calculator.lnk" "$INSTDIR\Start App.cmd" "" "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/gst-calculator/icon.ico" 0

  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR\app"
  Delete "$INSTDIR\Start App.cmd"
  Delete "$INSTDIR\launcher.py"
  Delete "$INSTDIR\app\app.json"
  RMDir "$INSTDIR"
  Delete "$DESKTOP\Tax & Tip Calculator.lnk"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\gst-calculator"
  DeleteRegKey HKCU "Software\Slingshot Tools\gst-calculator"
SectionEnd
