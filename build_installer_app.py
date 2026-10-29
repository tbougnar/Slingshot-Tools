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

import json
import os
import re
import shutil
import subprocess
import sys

# Windows consoles default to a legacy code page, so any non-ASCII character in
# model output used to raise UnicodeEncodeError and kill the run. Output that
# cannot be encoded is replaced rather than fatal.
for _stream in ("stdout", "stderr"):
    _s = getattr(sys, _stream, None)
    if _s is not None and hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def _safe(text) -> str:
    try:
        return str(text).encode("utf-8", "replace").decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return "<unprintable>"


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
    local = Path(os.environ.get("LOCALAPPDATA")
                 or Path.home() / "AppData" / "Local")
    for p in (r"C:\Program Files (x86)\NSIS\makensis.exe",
              r"C:\Program Files\NSIS\makensis.exe",
              r"C:\ProgramData\chocolatey\bin\makensis.exe",
              r"C:\ProgramData\chocolatey\lib\nsis\tools\makensis.exe",
              local / "Temp" / "nsis_x" / "makensis.exe"):
        if Path(p).exists():
            return str(p)
    return None


def _product_meta(app_folder: Path, title: str) -> tuple[str, str]:
    """(display version, four-number version) for the installer metadata.

    Apps & Features showed every product as "Slingshot Tools" version 1.0.0,
    so an update could not be told apart from the original install and the
    product's own name never appeared. The bundle's app.json is the source of
    truth; the fallback keeps an older bundle buildable.
    """
    meta: dict = {}
    for candidate in (app_folder / "app" / "app.json",
                      app_folder / "_internal" / "app" / "app.json"):
        try:
            got = json.loads(candidate.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if isinstance(got, dict):
            meta = got
            break
    version = str(meta.get("version") or "1.0.0").strip() or "1.0.0"
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?", version)
    quad = (f"{m.group(1)}.{m.group(2)}.{m.group(3)}.{m.group(4) or 0}"
            if m else "1.0.0.0")
    return version, quad


NSI = r"""
Unicode true
!include "MUI2.nsh"
!define APPNAME "{name}"
!define SLUG "{slug}"
!define VENDOR "Slingshot Tools"
!define PUBLISHER "Slingshot Tools"
!define VERSION "{version}"
!define OUT "{out}"

Name "{name}"
OutFile "${{OUT}}"
; Per-user, like the free launcher: no admin prompt, and the install folder is
; writable, so a tool that keeps its data beside the exe still works. A paid
; $3 download that opens a UAC box is also the single biggest drop-off there is.
InstallDir "$LOCALAPPDATA\Programs\Slingshot Tools\{name}"
InstallDirRegKey HKCU "Software\Slingshot\{slug}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma

VIProductVersion "{quad}"
VIAddVersionKey "ProductName" "{name}"
VIAddVersionKey "CompanyName" "Slingshot Tools"
VIAddVersionKey "FileDescription" "{name} by Slingshot Tools"
VIAddVersionKey "FileVersion" "{quad}"

!define MUI_ICON "{icon}"
!define MUI_UNICON "{icon}"
!define MUI_FINISHPAGE_RUN "$INSTDIR\{exe}"

; MUI pages only: "Page directory" beside MUI_PAGE_INSTFILES showed the
; progress page twice.
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Install"
  ; the whole app folder, including app\icon.ico which every icon below points at
  SetOutPath "$INSTDIR"
  File /r "{appdir}\*"

  WriteRegStr HKCU "Software\Slingshot\{slug}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{slug}" "DisplayName" "{name}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{slug}" "DisplayIcon" "$INSTDIR\app\icon.ico"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{slug}" "Publisher" "Slingshot Tools"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{slug}" "DisplayVersion" "{version}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{slug}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{slug}" "InstallLocation" "$INSTDIR"

  CreateDirectory "$SMPROGRAMS\{name}"
  CreateShortcut "$SMPROGRAMS\{name}\{name}.lnk" "$INSTDIR\{exe}"
  ; shortcuts point at the exe itself, so the shell shows the logo that is
  ; embedded in it rather than a blank page or another program's icon
  CreateShortcut "$SMPROGRAMS\{name}\Uninstall.lnk" "$INSTDIR\uninstall.exe"
  CreateShortcut "$DESKTOP\{name}.lnk" "$INSTDIR\{exe}"


  WriteUninstaller "$INSTDIR\uninstall.exe"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\{name}.lnk"
  RMDir /r "$SMPROGRAMS\{name}"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{slug}"
  DeleteRegKey HKCU "Software\Slingshot\{slug}"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'
SectionEnd
"""


def build_installer(app_folder: Path, title: str, paid_dir: Path | None = None) -> Path | None:
    # makensis resolves relative paths against the .nsi file's own folder (dist/),
    # so a caller that passed "dist/Thing/Thing" had every path doubled and the
    # build failed on the icon. Resolve once, here, whatever the caller passes.
    app_folder = Path(app_folder).resolve()
    paid_dir = Path(paid_dir).resolve() if paid_dir else None
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
        try:
            icon = make_ico(ICON_SRC, icon)
        except Exception as e:  # noqa: BLE001
            print(f"[nsis] could not convert the icon: {str(e)[:80]}",
                  flush=True)
            icon = None
    if not icon or not Path(icon).exists():
        # A Path is always truthy, so the old check passed with a path that
        # did not exist and makensis failed later on a bad MUI_ICON.
        print("[nsis] no icon available", flush=True)
        return None

    version, quad = _product_meta(app_folder, title)

    DIST.mkdir(exist_ok=True)
    out_exe = DIST / f"{title}-Setup.exe"
    # Removed before the build, not after a failure, so that the file's
    # existence always means "this build produced it". Leaving the previous
    # release's installer in place is how a failed compile could return last
    # week's binary as this week's.
    try:
        out_exe.unlink(missing_ok=True)
    except OSError as e:
        print(f"[nsis] could not remove the previous {out_exe.name}: {e}",
              flush=True)
        return None
    nsi = DIST / f"{title}.nsi"
    nsi.write_text(
        NSI.format(name=title, slug=title.lower().replace(" ", "-"),
                   out=str(out_exe).replace("\\", "/"),
                   appdir=str(app_folder).replace("\\", "/"),
                   icon=str(icon).replace("\\", "/"),
                   version=version, quad=quad,
                   exe=exe_name),
        encoding="utf-8")
    r = subprocess.run([makensis, str(nsi)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1200)
    # The return code was never checked. dist/<title>-Setup.exe from a previous
    # release was left in place, so a compile error, a timeout or a full disk
    # still left the old file there, and this returned it while printing
    # "installer built". The stale binary was then uploaded to itch.io as the
    # new version. Check the exit status first, and remove any previous
    # installer so the file's existence is evidence of this build and nothing
    # else.
    if r.returncode != 0:
        print(f"[nsis] FAILED rc={r.returncode}", flush=True)
        print(((r.stdout or "")[-400:] + (r.stderr or "")[-400:]), flush=True)
        try:
            out_exe.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    if not out_exe.exists():
        print(f"[nsis] FAILED rc={r.returncode}: no installer was produced",
              flush=True)
        print(((r.stdout or "")[-400:] + (r.stderr or "")[-400:]), flush=True)
        return None
    print(f"[nsis] installer built: {out_exe.name} "
          f"({out_exe.stat().st_size // 1024 // 1024} MB)", flush=True)
    return out_exe


if __name__ == "__main__":
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if p:
        print("OK" if build_installer(p, p.name, p) else "FAILED")