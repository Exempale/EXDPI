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
import sys
import traceback
from pathlib import Path
from typing import Optional


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


def _main_inner() -> int:
    if sys.platform == "win32" and not _is_admin():
        _relaunch_as_admin()
        return 0

    if getattr(sys, "frozen", False):
        try:
            os.chdir(Path(sys.executable).resolve().parent)
        except Exception:
            pass

    _setup_logging()
    import logging
    log = logging.getLogger("dpibypass.main")
    log.info("starting EXDPI")

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
