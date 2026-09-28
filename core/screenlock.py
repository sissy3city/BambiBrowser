"""Windows wallpaper-to-lock-screen synchronization for Bambi ScreenLock."""

import ctypes
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger("BambiBrowser.ScreenLock")

TASK_NAME = "BambiBrowserScreenLock"
SYNC_SCRIPT = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "BambiBrowserScreenLock.ps1"

_SYNC_SCRIPT = r'''$ErrorActionPreference = "Continue"
function Get-CurrentWallpaper {
    $sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $regPath = "Registry::HKEY_USERS\$sid\Control Panel\Desktop"
    $wallpaper = (Get-ItemProperty -Path $regPath -Name Wallpaper).Wallpaper
    if (-not $wallpaper) {
        $wallpaper = Join-Path $env:USERPROFILE "AppData\Roaming\Microsoft\Windows\Themes\TranscodedWallpaper"
    }
    if (Test-Path $wallpaper) { return $wallpaper }
}
function Update-LockScreen([string]$path) {
    if (-not $path) { return }
    $policy = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Personalization"
    $csp = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP"
    New-Item -Path $policy -Force | Out-Null
    New-Item -Path $csp -Force | Out-Null
    Set-ItemProperty -Path $policy -Name LockScreenImage -Value $path -Type String -Force
    Set-ItemProperty -Path $policy -Name NoChangingLockScreen -Value 1 -Type DWord -Force
    Set-ItemProperty -Path $csp -Name LockScreenImagePath -Value $path -Type String -Force
    Set-ItemProperty -Path $csp -Name LockScreenImageStatus -Value 1 -Type DWord -Force
}
$last = $null
while ($true) {
    $current = Get-CurrentWallpaper
    if ($current -and $current -ne $last) {
        Update-LockScreen $current
        $last = $current
    }
    Start-Sleep -Seconds 3
}
'''


def is_supported() -> bool:
    return os.name == "nt"


def is_admin() -> bool:
    if not is_supported():
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def is_enabled() -> bool:
    if not is_supported():
        return False
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return result.returncode == 0


def _task_state() -> str:
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST"],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        return "missing"
    for line in result.stdout.splitlines():
        if line.startswith("Status:"):
            return line.split(":", 1)[1].strip()
    return "unknown"


def _run_powershell(command: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def enable() -> tuple[bool, str]:
    if not is_supported():
        return False, "Bambi ScreenLock is only available on Windows."
    if not is_admin():
        return False, "Administrator rights are required for Bambi ScreenLock."
    try:
        SYNC_SCRIPT.write_text(_SYNC_SCRIPT, encoding="utf-8")
        result = _run_powershell(
            "$action = New-ScheduledTaskAction -Execute 'powershell.exe' "
            f"-Argument '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"{SYNC_SCRIPT}\"'; "
            "$trigger = New-ScheduledTaskTrigger -AtLogOn; "
            "$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries "
            "-DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 999 "
            "-RestartInterval (New-TimeSpan -Minutes 5); "
            "$principal = New-ScheduledTaskPrincipal -UserId "
            '"$env:USERDOMAIN\\$env:USERNAME" -LogonType Interactive -RunLevel Highest; '
            f"Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $action -Trigger $trigger "
            "-Settings $settings -Principal $principal -Force | Out-Null"
        )
        if result.returncode != 0:
            return False, result.stderr.strip() or "Could not create the ScreenLock scheduled task."
        policy_result = _run_powershell(
            r"$wallpaper = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\ActiveDesktop'; "
            r"$desktop = 'HKCU:\Software\Policies\Microsoft\Windows\Control Panel\Desktop'; "
            r"$explorer = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer'; "
            "New-Item -Path $wallpaper -Force | Out-Null; "
            "New-Item -Path $desktop -Force | Out-Null; "
            "New-Item -Path $explorer -Force | Out-Null; "
            "Set-ItemProperty -Path $wallpaper -Name NoChangingWallPaper -Value 1 -Type DWord -Force; "
            "Set-ItemProperty -Path $desktop -Name NoChangingWallPaper -Value 1 -Type DWord -Force; "
            "Set-ItemProperty -Path $explorer -Name NoSetDesktopBackground -Value 1 -Type DWord -Force; "
            "gpupdate.exe /target:user /force | Out-Null"
        )
        if policy_result.returncode != 0:
            return False, policy_result.stderr.strip() or "Could not apply wallpaper restrictions."
        start_result = _run_powershell(f"Start-ScheduledTask -TaskName '{TASK_NAME}'")
        if start_result.returncode != 0:
            return False, start_result.stderr.strip() or "Could not start the ScreenLock task."
        return True, "ScreenLock enabled and will follow the wallpaper at login."
    except Exception as exc:
        logger.exception("Failed to enable ScreenLock")
        return False, str(exc)


def disable() -> tuple[bool, str]:
    if not is_supported():
        return False, "Bambi ScreenLock is only available on Windows."
    if not is_admin():
        return False, "Administrator rights are required to disable Bambi ScreenLock."
    try:
        _run_powershell(f"Stop-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue")
        _run_powershell(f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false -ErrorAction SilentlyContinue")
        _run_powershell(
            "Get-CimInstance Win32_Process -Filter \"Name = 'powershell.exe'\" | "
            "Where-Object { $_.CommandLine -like '*BambiBrowserScreenLock.ps1*' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
        )
        if SYNC_SCRIPT.exists():
            SYNC_SCRIPT.unlink()
        _run_powershell(
            r"$policy = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Personalization'; "
            r"$csp = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP'; "
            "Remove-ItemProperty -Path $policy -Name NoChangingLockScreen,LockScreenImage -ErrorAction SilentlyContinue; "
            "Remove-ItemProperty -Path $csp -Name LockScreenImagePath,LockScreenImageStatus -ErrorAction SilentlyContinue"
        )
        _run_powershell(
            r"$wallpaper = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\ActiveDesktop'; "
            r"$desktop = 'HKCU:\Software\Policies\Microsoft\Windows\Control Panel\Desktop'; "
            r"$explorer = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer'; "
            "Remove-ItemProperty -Path $wallpaper -Name NoChangingWallPaper -ErrorAction SilentlyContinue; "
            "Remove-ItemProperty -Path $desktop -Name NoChangingWallPaper -ErrorAction SilentlyContinue; "
            "Remove-ItemProperty -Path $explorer -Name NoSetDesktopBackground -ErrorAction SilentlyContinue; "
            "gpupdate.exe /target:user /force | Out-Null"
        )
        return True, "ScreenLock disabled and its policy values were removed."
    except Exception as exc:
        logger.exception("Failed to disable ScreenLock")
        return False, str(exc)