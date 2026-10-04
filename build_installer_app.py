"""Wrap the built app folder in an NSIS installer.

Three things the old installer got wrong and that are fixed here:
  * the Start Menu and Desktop shortcuts point straight at the .exe, so no
    console window flashes and no terminal tab opens
  * every icon - shortcut, Start Menu, Apps & Features, taskbar - comes from an
    .ico installed next to the exe, so the company logo shows everywhere
    instead of Python's or a blank page
  * DisplayIcon points inside the install folder, not at a path that only
    exists on the machine that built it
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"


ICON_SRC = ROOT / "site" / "icon-512.png"


def src_ok(p):
    return Path(p).exists()


def _find_makensis() -> str | None:
    exe = shutil.which("makensis")
    if exe:
        return exe
    for p in (r"C:\Program Files (x86)\NSIS\makensis.exe",
              r"C:\Program Files\NSIS\makensis.exe",
              r"C:\Users\Taha\AppData\Local\Temp\nsis_x\makensis.exe"):
        if Path(p).exists():
            return p
    return None


NSI = r"""
Unicode true
!include "MUI2.nsh"
!define APPNAME "{name}"
!define SLUG "{slug}"
!define VENDOR "Slingshot Tools"
!define PUBLISHER "Slingshot Tools"
!define VERSION "1.0.0"
!define OUT "{out}"

Name "Slingshot Tools"
OutFile "${{OUT}}"
InstallDir "$PROGRAMFILES64\{name}"
InstallDirRegKey HKLM "Software\Slingshot\{slug}" "InstallDir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

VIProductVersion "1.0.0.0"
VIAddVersionKey "ProductName" "Slingshot Tools"
VIAddVersionKey "CompanyName" "Slingshot Tools"
VIAddVersionKey "FileDescription" "Slingshot Tools"
VIAddVersionKey "FileVersion" "1.0.0.0"

!define MUI_ICON "{icon}"
!define MUI_UNICON "{icon}"
!define MUI_FINISHPAGE_RUN "$INSTDIR\{name}\{exe}"

Page directory
Page instfiles
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

UninstPage instfiles
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

Section "Install"
  ; the whole app folder, including app\icon.ico which every icon below points at
  SetOutPath "$INSTDIR\{name}"
  File /r "{appdir}\*"

  WriteRegStr HKLM "Software\Slingshot\{slug}" "InstallDir" "$INSTDIR\{name}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\{slug}" "DisplayName" "{name}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\{slug}" "DisplayIcon" "$INSTDIR\{name}\app\icon.ico"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\{slug}" "Publisher" "Slingshot Tools"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\{slug}" "DisplayVersion" "1.0.0"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\{slug}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\{slug}" "InstallLocation" "$INSTDIR\{name}"

  CreateDirectory "$SMPROGRAMS\{name}"
  CreateShortcut "$SMPROGRAMS\{name}\{name}.lnk" "$INSTDIR\{name}\{exe}"
  ; shortcuts point at the exe itself, so the shell shows the logo that is
  ; embedded in it rather than a blank page or another program's icon
  CreateShortcut "$SMPROGRAMS\{name}\Uninstall.lnk" "$INSTDIR\uninstall.exe"
  CreateShortcut "$DESKTOP\{name}.lnk" "$INSTDIR\{name}\{exe}"


  WriteUninstaller "$INSTDIR\uninstall.exe"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\{name}.lnk"
  RMDir /r "$SMPROGRAMS\{name}"
  RMDir /r "$INSTDIR\{name}"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\{slug}"
  DeleteRegKey HKLM "Software\Slingshot\{slug}"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'
SectionEnd
"""


def build_installer(app_folder: Path, title: str, paid_dir: Path | None = None) -> Path | None:
    makensis = _find_makensis()
    if not makensis:
        print("[nsis] makensis not found - cannot build the installer", flush=True)
        return None

    exe_name = f"{title}.exe"
    if not (app_folder / exe_name).exists():
        print(f"[nsis] no app exe at {app_folder / exe_name}", flush=True)
        return None

    from build_exe import make_ico
    (app_folder / "app").mkdir(parents=True, exist_ok=True)
    icon = app_folder / "app" / "icon.ico"
    if not icon.exists() and src_ok(ICON_SRC):
        icon = make_ico(ICON_SRC, icon)
    if not icon:
        print("[nsis] no icon available", flush=True)
        return None

    DIST.mkdir(exist_ok=True)
    out_exe = DIST / f"{title}-Setup.exe"
    nsi = DIST / f"{title}.nsi"
    nsi.write_text(
        NSI.format(name=title, slug=title.lower().replace(" ", "-"),
                   out=str(out_exe).replace("\\", "/"),
                   appdir=str(app_folder).replace("\\", "/"),
                   paidir=str(paid_dir or app_folder).replace("\\", "/"),
                   icon=str(icon).replace("\\", "/"),
                   exe=exe_name),
        encoding="utf-8")
    r = subprocess.run([makensis, str(nsi)], capture_output=True, text=True, timeout=1200)
    if not out_exe.exists():
        print(f"[nsis] FAILED rc={r.returncode}", flush=True)
        print(((r.stdout or "")[-400:] + (r.stderr or "")[-400:]), flush=True)
        return None
    print(f"[nsis] installer built: {out_exe.name} "
          f"({out_exe.stat().st_size // 1024 // 1024} MB)", flush=True)
    return out_exe


if __name__ == "__main__":
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if p:
        print("OK" if build_installer(p, p.name, p) else "FAILED")