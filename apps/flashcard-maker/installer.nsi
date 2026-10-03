
; Slingshot Tool installer - built by Slingshot Tools
Unicode true
!define APPNAME "Spaced Flashcards"
!define BRAND "Slingshot Tools"
!define SLUG "flashcard-maker"
!define VENDOR "Slingshot Tools"
!define PUBLISHER_URL "https://https://tbougnar.github.io/Slingshot-Tools"
Name "Spaced Flashcards"
OutFile "/home/runner/work/Slingshot-Tools/Slingshot-Tools/dist/SlingshotTool-flashcard-maker-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\Slingshot Tools\flashcard-maker"
InstallDirRegKey HKCU "Software\Slingshot Tools\flashcard-maker" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Unicode true

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/flashcard-maker/icon.ico"
!define MUI_UNICON "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/flashcard-maker/icon.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\Start App.cmd"
!define MUI_FINISHPAGE_RUN_TEXT "Start Spaced Flashcards"

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

  WriteRegStr HKCU "Software\Slingshot Tools\flashcard-maker" "InstallDir" "$INSTDIR"

  ; Start Menu + Desktop shortcuts launch the app in a chromeless app window
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\flashcard-maker" "DisplayName" "Spaced Flashcards"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\flashcard-maker" "Publisher" "$VENDOR"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\flashcard-maker" "DisplayVersion" "1.0.0"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\flashcard-maker" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\flashcard-maker" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\flashcard-maker" "DisplayIcon" "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/flashcard-maker/icon.ico"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\flashcard-maker" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\flashcard-maker" "NoRepair" 1

  CreateShortcut "$SMPROGRAMS\Spaced Flashcards.lnk" "$INSTDIR\Start App.cmd" "" "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/flashcard-maker/icon.ico" 0
  CreateShortcut "$SMPROGRAMS\Uninstall Spaced Flashcards.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\Spaced Flashcards.lnk" "$INSTDIR\Start App.cmd" "" "/home/runner/work/Slingshot-Tools/Slingshot-Tools/apps/flashcard-maker/icon.ico" 0

  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR\app"
  Delete "$INSTDIR\Start App.cmd"
  Delete "$INSTDIR\launcher.py"
  Delete "$INSTDIR\app\app.json"
  RMDir "$INSTDIR"
  Delete "$DESKTOP\Spaced Flashcards.lnk"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\flashcard-maker"
  DeleteRegKey HKCU "Software\Slingshot Tools\flashcard-maker"
SectionEnd
