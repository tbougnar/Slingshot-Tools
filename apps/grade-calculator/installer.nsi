
; Slingshot Tool installer - built by Slingshot Tools
Unicode true
!define APPNAME "Grade Calculator"
!define BRAND "Slingshot Tools"
!define SLUG "grade-calculator"
!define VENDOR "Slingshot Tools"
!define PUBLISHER_URL "https://https://tbougnar.github.io/Slingshot-Tools"
Name "Grade Calculator"
OutFile "/home/runner/work/Slingshot-Tools/Slingshot-Tools/dist/SlingshotTool-grade-calculator-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\Slingshot Tools\grade-calculator"
InstallDirRegKey HKCU "Software\Slingshot Tools\grade-calculator" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Unicode true

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/grade-calculator/icon.ico"
!define MUI_UNICON "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/grade-calculator/icon.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\Start App.cmd"
!define MUI_FINISHPAGE_RUN_TEXT "Start Grade Calculator"

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

  WriteRegStr HKCU "Software\Slingshot Tools\grade-calculator" "InstallDir" "$INSTDIR"

  ; Start Menu + Desktop shortcuts launch the app in a chromeless app window
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\grade-calculator" "DisplayName" "Grade Calculator"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\grade-calculator" "Publisher" "$VENDOR"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\grade-calculator" "DisplayVersion" "1.0.0"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\grade-calculator" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\grade-calculator" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\grade-calculator" "DisplayIcon" "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/grade-calculator/icon.ico"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\grade-calculator" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\grade-calculator" "NoRepair" 1

  CreateShortcut "$SMPROGRAMS\Grade Calculator.lnk" "$INSTDIR\Start App.cmd" "" "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/grade-calculator/icon.ico" 0
  CreateShortcut "$SMPROGRAMS\Uninstall Grade Calculator.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\Grade Calculator.lnk" "$INSTDIR\Start App.cmd" "" "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/grade-calculator/icon.ico" 0

  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR\app"
  Delete "$INSTDIR\Start App.cmd"
  Delete "$INSTDIR\launcher.py"
  Delete "$INSTDIR\app\app.json"
  RMDir "$INSTDIR"
  Delete "$DESKTOP\Grade Calculator.lnk"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\grade-calculator"
  DeleteRegKey HKCU "Software\Slingshot Tools\grade-calculator"
SectionEnd
