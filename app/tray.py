"""Иконка в системном трее (Windows notification area).

Тонкая обёртка над pystray. Минимальное меню:
  - Открыть EXDPI
  - Включить / Выключить (динамическая надпись)
  - Выход

UI-callback'и должны быть thread-safe со стороны вызывающего кода —
pystray дёргает их из своего внутреннего потока.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("dpibypass.tray")


class TrayController:
    """Запуск/остановка tray-иконки в отдельном потоке."""

    def __init__(
        self,
        icon_path: Path,
        on_show: Callable[[], None],
        on_toggle: Callable[[], None],
        on_quit: Callable[[], None],
        is_on_provider: Callable[[], bool],
    ) -> None:
        self._icon_path = icon_path
        self._on_show = on_show
        self._on_toggle = on_toggle
        self._on_quit = on_quit
        self._is_on_provider = is_on_provider

        self._icon = None  # type: ignore[assignment]
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> bool:
        """Создаёт иконку и запускает её цикл в фоновом потоке."""
        try:
            import pystray  # type: ignore
            from PIL import Image  # type: ignore
        except ImportError as exc:
            log.warning("tray unavailable: %s", exc)
            return False

        try:
            image = Image.open(str(self._icon_path))
        except Exception as exc:
            log.warning("tray icon load failed: %s", exc)
            return False

        def _toggle_label(_icon) -> str:
            try:
                return "Выключить" if self._is_on_provider() else "Включить"
            except Exception:
                return "Переключить"

        def _click_show(_icon, _item):
            try:
                self._on_show()
            except Exception:
                log.exception("tray show callback failed")

        def _click_toggle(_icon, _item):
            try:
                self._on_toggle()
            except Exception:
                log.exception("tray toggle callback failed")

        def _click_quit(icon, _item):
            try:
                self._on_quit()
            except Exception:
                log.exception("tray quit callback failed")
            try:
                icon.stop()
            except Exception:
                pass

        menu = pystray.Menu(
            pystray.MenuItem("Открыть EXDPI", _click_show, default=True),
            pystray.MenuItem(_toggle_label, _click_toggle),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", _click_quit),
        )

        self._icon = pystray.Icon(
            "EXDPI",
            icon=image,
            title="EXDPI",
            menu=menu,
        )

        def _runloop():
            try:
                self._icon.run()  # type: ignore[union-attr]
            except Exception:
                log.exception("tray runloop crashed")
            finally:
                self._running = False

        self._thread = threading.Thread(
            target=_runloop, daemon=True, name="exdpi-tray",
        )
        self._thread.start()
        self._running = True
        return True

    def update_state(self) -> None:
        """Перерисовать меню (например, чтобы Включить ⇄ Выключить
        обновилось после смены состояния)."""
        if not self._icon:
            return
        try:
            self._icon.update_menu()  # type: ignore[union-attr]
        except Exception:
            pass

    def notify(self, message: str, title: str = "EXDPI") -> None:
        if not self._icon:
            return
        try:
            self._icon.notify(message, title)  # type: ignore[union-attr]
        except Exception:
            pass

    def stop(self) -> None:
        if not self._icon:
            return
        try:
            self._icon.stop()  # type: ignore[union-attr]
        except Exception:
            pass
        self._running = False
