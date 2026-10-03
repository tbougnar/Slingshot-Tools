
; Slingshot Tool installer - built by Slingshot Tools
Unicode true
!define APPNAME "Batch Rename"
!define BRAND "Slingshot Tools"
!define SLUG "file-renamer"
!define VENDOR "Slingshot Tools"
!define PUBLISHER_URL "https://https://tbougnar.github.io/Slingshot-Tools"
Name "Batch Rename"
OutFile "/home/runner/work/Slingshot-Tools/Slingshot-Tools/dist/SlingshotTool-file-renamer-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\Slingshot Tools\file-renamer"
InstallDirRegKey HKCU "Software\Slingshot Tools\file-renamer" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Unicode true

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/file-renamer/icon.ico"
!define MUI_UNICON "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/file-renamer/icon.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\Start App.cmd"
!define MUI_FINISHPAGE_RUN_TEXT "Start Batch Rename"

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

  WriteRegStr HKCU "Software\Slingshot Tools\file-renamer" "InstallDir" "$INSTDIR"

  ; Start Menu + Desktop shortcuts launch the app in a chromeless app window
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\file-renamer" "DisplayName" "Batch Rename"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\file-renamer" "Publisher" "$VENDOR"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\file-renamer" "DisplayVersion" "1.0.0"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\file-renamer" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\file-renamer" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\file-renamer" "DisplayIcon" "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/file-renamer/icon.ico"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\file-renamer" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\file-renamer" "NoRepair" 1

  CreateShortcut "$SMPROGRAMS\Batch Rename.lnk" "$INSTDIR\Start App.cmd" "" "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/file-renamer/icon.ico" 0
  CreateShortcut "$SMPROGRAMS\Uninstall Batch Rename.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\Batch Rename.lnk" "$INSTDIR\Start App.cmd" "" "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/file-renamer/icon.ico" 0

  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR\app"
  Delete "$INSTDIR\Start App.cmd"
  Delete "$INSTDIR\launcher.py"
  Delete "$INSTDIR\app\app.json"
  RMDir "$INSTDIR"
  Delete "$DESKTOP\Batch Rename.lnk"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\file-renamer"
  DeleteRegKey HKCU "Software\Slingshot Tools\file-renamer"
SectionEnd
