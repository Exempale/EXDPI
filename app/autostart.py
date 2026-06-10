"""Авто-запуск EXDPI вместе с Windows.

EXDPI требует прав администратора (winws.exe ставит WinDivert-фильтр на
сетевом уровне, манифест — requireAdministrator). Из-за этого ставшая
«классической» автозагрузка через ключ реестра
``HKCU\\...\\CurrentVersion\\Run`` НЕ РАБОТАЕТ: Windows не может показать
UAC-промпт во время входа в систему и просто молча пропускает запись.

Поэтому автозапуск реализован через Планировщик заданий (schtasks):
создаётся задача с триггером «при входе пользователя» и уровнем запуска
``HighestAvailable`` — она стартует приложение уже с правами администратора
и без всплывающего UAC. Старый ключ Run при этом подчищается (миграция).

На не-Windows платформах все функции — no-op.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

log = logging.getLogger("dpibypass.autostart")


# Имя задачи в Планировщике (видно в taskschd.msc).
TASK_NAME = "EXDPI Autostart"

# Легаси: ключ автозагрузки, который использовался раньше. Чистим при apply().
_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "EXDPI"

_CREATE_NO_WINDOW = 0x08000000


def _exe_path() -> Optional[str]:
    """Путь к .exe, который пишем в задачу автозапуска.

    В onefile-сборке PyInstaller это сам EXDPI.exe (sys.executable).
    В development-режиме (запуск из python) возвращаем None, чтобы не
    регистрировать python.exe в автозагрузке случайно.
    """
    if not getattr(sys, "frozen", False):
        return None
    exe = sys.executable
    try:
        return str(Path(exe).resolve())
    except Exception:
        return exe


def _run(args: list[str], timeout: float = 10.0) -> Optional[subprocess.CompletedProcess]:
    """Запустить консольную утилиту тихо (без мелькающего окна)."""
    if sys.platform != "win32":
        return None
    try:
        return subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            creationflags=_CREATE_NO_WINDOW,
            timeout=timeout,
        )
    except Exception as exc:
        log.warning("command failed %s: %s", args[:2], exc)
        return None


# ── Планировщик заданий ──────────────────────────────────────────────

def _xml_escape(s: str) -> str:
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;")
        .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")
    )


def _current_user_id() -> str:
    user = os.environ.get("USERNAME", "") or ""
    domain = os.environ.get("USERDOMAIN") or os.environ.get("COMPUTERNAME") or ""
    if domain and user:
        return f"{domain}\\{user}"
    return user


def _task_xml(exe: str) -> str:
    """Сгенерировать XML задачи: вход пользователя → запуск EXDPI с правами
    администратора (HighestAvailable, без UAC-промпта)."""
    user_id = _xml_escape(_current_user_id())
    exe_esc = _xml_escape(exe)
    return (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.2" '
        'xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        "  <RegistrationInfo>\n"
        "    <Description>EXDPI — автозапуск при входе в Windows</Description>\n"
        "  </RegistrationInfo>\n"
        "  <Triggers>\n"
        "    <LogonTrigger>\n"
        "      <Enabled>true</Enabled>\n"
        f"      <UserId>{user_id}</UserId>\n"
        "    </LogonTrigger>\n"
        "  </Triggers>\n"
        "  <Principals>\n"
        '    <Principal id="Author">\n'
        f"      <UserId>{user_id}</UserId>\n"
        "      <LogonType>InteractiveToken</LogonType>\n"
        "      <RunLevel>HighestAvailable</RunLevel>\n"
        "    </Principal>\n"
        "  </Principals>\n"
        "  <Settings>\n"
        "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n"
        "    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n"
        "    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n"
        "    <AllowHardTerminate>true</AllowHardTerminate>\n"
        "    <StartWhenAvailable>false</StartWhenAvailable>\n"
        "    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>\n"
        "    <IdleSettings>\n"
        "      <StopOnIdleEnd>false</StopOnIdleEnd>\n"
        "      <RestartOnIdle>false</RestartOnIdle>\n"
        "    </IdleSettings>\n"
        "    <AllowStartOnDemand>true</AllowStartOnDemand>\n"
        "    <Enabled>true</Enabled>\n"
        "    <Hidden>false</Hidden>\n"
        "    <RunOnlyIfIdle>false</RunOnlyIfIdle>\n"
        "    <WakeToRun>false</WakeToRun>\n"
        "    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>\n"
        "    <Priority>7</Priority>\n"
        "  </Settings>\n"
        '  <Actions Context="Author">\n'
        "    <Exec>\n"
        f"      <Command>{exe_esc}</Command>\n"
        "    </Exec>\n"
        "  </Actions>\n"
        "</Task>\n"
    )


def _task_exists() -> bool:
    res = _run(["schtasks", "/query", "/tn", TASK_NAME])
    return bool(res is not None and res.returncode == 0)


def _create_task(exe: str) -> bool:
    """Создать/перезаписать задачу автозапуска из XML."""
    xml = _task_xml(exe)
    tmp_path: Optional[str] = None
    try:
        # schtasks /xml требует Unicode (UTF-16) файл.
        fd, tmp_path = tempfile.mkstemp(suffix=".xml", prefix="exdpi_task_")
        os.close(fd)
        with open(tmp_path, "w", encoding="utf-16") as fp:
            fp.write(xml)
        res = _run([
            "schtasks", "/create", "/tn", TASK_NAME,
            "/xml", tmp_path, "/f",
        ])
        if res is None:
            return False
        if res.returncode != 0:
            err = (res.stderr or b"").decode("cp866", errors="replace").strip()
            log.warning("schtasks create failed rc=%s: %s", res.returncode, err)
            return False
        log.info("autostart task created: %s -> %s", TASK_NAME, exe)
        return True
    except Exception:
        log.exception("create task failed")
        return False
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def _delete_task() -> bool:
    if not _task_exists():
        return True
    res = _run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"])
    if res is None:
        return False
    if res.returncode != 0:
        err = (res.stderr or b"").decode("cp866", errors="replace").strip()
        log.warning("schtasks delete failed rc=%s: %s", res.returncode, err)
        return False
    log.info("autostart task deleted: %s", TASK_NAME)
    return True


# ── Легаси Run-ключ (только чистим) ──────────────────────────────────

def _remove_legacy_run_value() -> None:
    """Удалить старую запись HKCU\\...\\Run, если она осталась от прошлых версий."""
    if sys.platform != "win32":
        return
    try:
        import winreg  # type: ignore
    except ImportError:
        return
    try:
        key = winreg.OpenKeyEx(
            winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0,
            winreg.KEY_READ | winreg.KEY_WRITE,
        )
    except OSError:
        return
    try:
        try:
            winreg.DeleteValue(key, _VALUE_NAME)
            log.info("removed legacy Run autostart entry")
        except FileNotFoundError:
            pass
        except OSError as exc:
            log.warning("failed to remove legacy Run entry: %s", exc)
    finally:
        try:
            winreg.CloseKey(key)
        except Exception:
            pass


# ── Публичный API ────────────────────────────────────────────────────

def is_enabled() -> bool:
    """True, если задача автозапуска существует в Планировщике."""
    if sys.platform != "win32":
        return False
    return _task_exists()


def enable() -> bool:
    """Создать/обновить задачу автозапуска. Возвращает True при успехе."""
    if sys.platform != "win32":
        log.info("autostart enable skipped: not on Windows")
        return False
    exe = _exe_path()
    if not exe:
        log.info("autostart enable skipped: not running from frozen exe")
        return False
    ok = _create_task(exe)
    # старый Run-ключ больше не нужен — убираем, чтобы не плодить дубли
    _remove_legacy_run_value()
    return ok


def disable() -> bool:
    """Удалить задачу автозапуска (и легаси Run-ключ). True при успехе/отсутствии."""
    if sys.platform != "win32":
        return False
    ok = _delete_task()
    _remove_legacy_run_value()
    return ok


def apply(want_enabled: bool) -> None:
    """Привести состояние автозапуска к заданному. Тихо, ошибки логируются.

    При включении задача всегда пересоздаётся — так путь к .exe остаётся
    актуальным, даже если пользователь переместил программу.
    """
    if sys.platform != "win32":
        return
    try:
        if want_enabled:
            enable()
        else:
            disable()
    except Exception:
        log.exception("autostart apply failed")
