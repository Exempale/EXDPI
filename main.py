"""Точка входа EXDPI.

Объединённый GUI для:
  • zapret-discord-youtube (winws.exe — DPI обход)
  • tg-ws-proxy           (MTProto WebSocket-прокси Telegram)

При запуске не от администратора — автоматически перезапускается
от имени администратора через UAC (ShellExecuteW + runas).
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Optional


def _enable_dpi_awareness() -> None:
    """Сообщить Windows, что приложение само рисует под High-DPI.

    Без этого Tk-окно растягивается через bitmap-scaling — иконка в панели
    задач и сам интерфейс выглядят замыленными на HiDPI-экранах.
    """
    if sys.platform != "win32":
        return
    try:
        # Per-Monitor v2 (Windows 10 1703+). Если ОС старее — упадёт, тогда fallback.
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _set_app_user_model_id() -> None:
    """Чтобы Windows объединяла окна EXDPI и брала нашу иконку, а не Python.exe."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Exempale.EXDPI")
    except Exception:
        pass


def _is_admin() -> bool:
    if sys.platform != "win32":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_as_admin() -> None:
    if sys.platform != "win32":
        return
    try:
        params = " ".join(f'"{a}"' for a in sys.argv[1:])
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1,
        )
        if int(rc) <= 32:
            ctypes.windll.user32.MessageBoxW(
                None,
                "Программе нужны права администратора.\n\n"
                "Запустите от имени администратора и попробуйте снова.",
                "EXDPI",
                0x10,
            )
    except Exception:
        pass


def _crash_log_candidates() -> list[Path]:
    """Места, куда пытаемся писать дамп; пишем в первый успешный."""
    out: list[Path] = []
    if getattr(sys, "frozen", False):
        try:
            out.append(Path(sys.executable).resolve().parent / "EXDPI-crash.log")
        except Exception:
            pass
    appdata = os.environ.get("APPDATA")
    if appdata:
        out.append(Path(appdata) / "EXDPI" / "EXDPI-crash.log")
    tmp = os.environ.get("TEMP") or os.environ.get("TMP")
    if tmp:
        out.append(Path(tmp) / "EXDPI-crash.log")
    try:
        out.append(Path.home() / "EXDPI-crash.log")
    except Exception:
        pass
    return out


def _write_crash(exc: BaseException) -> Path:
    last_err: Optional[Path] = None  # type: ignore[name-defined]
    for path in _crash_log_candidates():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fp:
                fp.write("EXDPI — crash report\n")
                fp.write(f"python: {sys.version}\n")
                fp.write(f"frozen: {getattr(sys, 'frozen', False)}\n")
                fp.write(f"executable: {sys.executable}\n")
                fp.write(f"argv: {sys.argv}\n")
                fp.write(f"cwd: {os.getcwd()}\n")
                fp.write("sys.path:\n  " + "\n  ".join(sys.path) + "\n")
                fp.write("=" * 60 + "\n")
                traceback.print_exception(type(exc), exc, exc.__traceback__, file=fp)
            return path
        except Exception:
            last_err = path
            continue
    return last_err or Path.home() / "EXDPI-crash.log"


def _show_crash_messagebox(exc: BaseException, log_path: Path) -> None:
    if sys.platform != "win32":
        return
    try:
        text = (
            f"EXDPI упал при запуске:\n\n"
            f"{type(exc).__name__}: {exc}\n\n"
            f"Полный лог: {log_path}\n\n"
            f"Пришли его в чат, и я починю."
        )
        ctypes.windll.user32.MessageBoxW(None, text, "EXDPI — ошибка", 0x10)
    except Exception:
        pass


def _setup_logging() -> None:
    import logging
    try:
        from app.config import app_dir
        d = app_dir()
        d.mkdir(parents=True, exist_ok=True)
        log_path = d / "exdpi.log"
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s  %(levelname)-5s  %(name)s  %(message)s",
            handlers=[logging.FileHandler(str(log_path), encoding="utf-8")],
        )
    except Exception:
        logging.basicConfig(level=logging.INFO)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


_SINGLE_INSTANCE_MUTEX = None  # глобал — мьютекс держим живым весь процесс


def _acquire_single_instance() -> bool:
    """Не дать запустить второй экземпляр EXDPI.

    Без этой защиты пользователь дважды кликал по .exe → второй процесс
    получал OSError 10048 (порт 1443 занят) и rc=1 от winws.exe из-за
    конфликта WinDivert-фильтров.
    """
    global _SINGLE_INSTANCE_MUTEX
    if sys.platform != "win32":
        return True
    try:
        ERROR_ALREADY_EXISTS = 183
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p,
        ]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        # Global\\ — общий для всех сессий (нужны права администратора).
        handle = kernel32.CreateMutexW(None, 0, "Global\\EXDPI_SingleInstance")
        last_err = kernel32.GetLastError()
        if not handle:
            return True
        if last_err == ERROR_ALREADY_EXISTS:
            try:
                ctypes.windll.user32.MessageBoxW(
                    None,
                    "EXDPI уже запущен.\n\n"
                    "Найдите иконку в системном трее или закройте старый процесс "
                    "(Диспетчер задач → EXDPI.exe).",
                    "EXDPI",
                    0x40,
                )
            except Exception:
                pass
            return False
        _SINGLE_INSTANCE_MUTEX = handle
        return True
    except Exception:
        return True


def _kill_orphan_winws_startup() -> None:
    """Убить осиротевший winws.exe от прошлой сессии EXDPI, если такой висит."""
    if sys.platform != "win32":
        return
    try:
        CREATE_NO_WINDOW = 0x08000000
        subprocess.run(
            ["taskkill", "/F", "/IM", "winws.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            timeout=5,
        )
    except Exception:
        pass


def _main_inner() -> int:
    if sys.platform == "win32" and not _is_admin():
        _relaunch_as_admin()
        return 0

    if not _acquire_single_instance():
        return 0

    _kill_orphan_winws_startup()
    _enable_dpi_awareness()
    _set_app_user_model_id()

    if getattr(sys, "frozen", False):
        try:
            os.chdir(Path(sys.executable).resolve().parent)
        except Exception:
            pass

    _setup_logging()
    import logging
    log = logging.getLogger("dpibypass.main")
    log.info("starting EXDPI")

    # Применяем сохранённую тему ДО создания виджетов — у tkinter нельзя
    # просто «переопределить bg=…» для виджета задним числом без передёргивания.
    try:
        from app import config as appconfig
        from app.theme import apply_theme
        _cfg = appconfig.load()
        apply_theme(str(_cfg.get("theme", "dark")))
    except Exception:
        logging.getLogger("dpibypass.main").exception("apply theme failed")

    from app.ui_app import App

    app = App()
    try:
        app.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            app.ctl.stop()
        except Exception:
            pass
    return 0


def main() -> int:
    try:
        return _main_inner()
    except SystemExit:
        raise
    except BaseException as exc:
        log_path = _write_crash(exc)
        _show_crash_messagebox(exc, log_path)
        return 1


if __name__ == "__main__":
    sys.exit(main())
