"""Иконка в системном трее (Windows notification area) с быстрым меню.

Меню:
  - строка статуса (вкл/выкл · стратегия);
  - Открыть EXDPI (default, по двойному клику);
  - Включить / Выключить;
  - Стратегия → radio-список general*.bat + «Авто»;
  - Режим → обычный / гейминг;
  - Проверить обход (DPI-тест);
  - Папка с логами;
  - Настройки;
  - Выход.

Иконка динамическая: в углу рисуется точка-индикатор (зелёная — обход
включён, серая — выключен).

UI-callback'и дёргаются из потока pystray — вызывающий код обязан бунсить
их в Tk-loop через self.after(0, ...).
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

log = logging.getLogger("dpibypass.tray")


_MODE_LABELS = (("normal", "Обычный"), ("gaming", "Гейминг"))
_APP_MODE_LABELS = (("dpi", "DPI-обход"), ("vpn", "VPN"))


class TrayController:
    """Запуск/остановка tray-иконки в отдельном потоке."""

    def __init__(
        self,
        icon_path: Path,
        on_show: Callable[[], None],
        on_toggle: Callable[[], None],
        on_quit: Callable[[], None],
        is_on_provider: Callable[[], bool],
        cfg_provider: Optional[Callable[[], Dict]] = None,
        on_strategy: Optional[Callable[[str], None]] = None,
        on_mode: Optional[Callable[[str], None]] = None,
        on_app_mode: Optional[Callable[[str], None]] = None,
        on_dpitest: Optional[Callable[[], None]] = None,
        on_logs: Optional[Callable[[], None]] = None,
        on_settings: Optional[Callable[[], None]] = None,
    ) -> None:
        self._icon_path = icon_path
        self._on_show = on_show
        self._on_toggle = on_toggle
        self._on_quit = on_quit
        self._is_on_provider = is_on_provider
        self._cfg_provider = cfg_provider
        self._on_strategy = on_strategy
        self._on_mode = on_mode
        self._on_app_mode = on_app_mode
        self._on_dpitest = on_dpitest
        self._on_logs = on_logs
        self._on_settings = on_settings

        self._icon = None  # type: ignore[assignment]
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._img_on = None
        self._img_off = None
        self._last_on: Optional[bool] = None

    # ── helpers ──────────────────────────────────────────────────────

    def _is_on(self) -> bool:
        try:
            return bool(self._is_on_provider())
        except Exception:
            return False

    def _cfg(self) -> Dict:
        if self._cfg_provider is None:
            return {}
        try:
            return self._cfg_provider() or {}
        except Exception:
            return {}

    @staticmethod
    def _strategy_short(name: str) -> str:
        """general (ALT10).bat → ALT10; general.bat → general."""
        n = name
        if n.endswith(".bat"):
            n = n[:-4]
        if n.startswith("general"):
            n = n[len("general"):].strip()
        n = n.strip("()").strip()
        return n or "general"

    def _make_status_images(self):
        """Базовая иконка + точка-индикатор (зелёная/серая) в правом нижнем углу.

        Возвращает (img_on, img_off) — оба PIL.Image, не сохраняются между вызовами
        до успешного старта, чтобы падение не оставляло полусобранное состояние.
        """
        from PIL import Image, ImageDraw  # type: ignore

        base = Image.open(str(self._icon_path)).convert("RGBA")
        size = base.size[0]
        r = max(5, size // 4)
        pad = max(1, size // 32)

        def with_dot(color: str):
            img = base.copy()
            draw = ImageDraw.Draw(img)
            x1, y1 = size - 2 * r - pad, size - 2 * r - pad
            x2, y2 = size - pad, size - pad
            draw.ellipse((x1, y1, x2, y2), fill=color, outline=(20, 20, 20, 255), width=max(1, size // 64))
            return img

        return with_dot("#22c55e"), with_dot("#6b7280")

    # ── lifecycle ────────────────────────────────────────────────────

    def start(self) -> bool:
        """Создаёт иконку и запускает её цикл в фоновом потоке.

        pystray.Icon должен создаваться И работать (= run()) в одном и том же
        потоке на Windows — иначе сообщения иконки трея не доставляются и
        меню не открывается. Поэтому всё, от импорта pystray до run(), делаем
        внутри фонового потока. Старт считается успешным, когда иконка
        реально показалась (через ``ready``-event в setup-callback).
        """
        try:
            self._img_on, self._img_off = self._make_status_images()
        except Exception as exc:
            log.warning("tray icon load failed: %s", exc)
            return False

        self._last_on = self._is_on()
        started = threading.Event()
        failed = threading.Event()

        def _runloop() -> None:
            try:
                import pystray  # type: ignore
            except ImportError as exc:
                log.warning("tray unavailable: %s", exc)
                failed.set()
                return

            try:
                menu = self._build_menu(pystray)
                icon = pystray.Icon(
                    "EXDPI",
                    icon=self._img_on if self._last_on else self._img_off,
                    title="EXDPI",
                    menu=menu,
                )
            except Exception:
                log.exception("tray icon construction failed")
                failed.set()
                return

            self._icon = icon

            def _notify_started(ic):  # вызывается pystray после показа иконки
                started.set()

            try:
                # pystray передаёт setup первым позиционным аргументом на win32
                icon.run(setup=_notify_started)
            except TypeError:
                # setup не поддержан (или под-Windows отобалован сигнатурой) —
                # запускаем вручную: отдельно прогоняем setup, потом run().
                try:
                    started.set()
                    _notify_started(icon)
                    icon.run()
                except Exception:
                    log.exception("tray runloop crashed")
                    failed.set()
            except Exception:
                log.exception("tray runloop crashed")
                if not started.is_set():
                    failed.set()
            finally:
                self._running = False
                self._icon = None

        self._thread = threading.Thread(
            target=_runloop, daemon=True, name="exdpi-tray",
        )
        self._thread.start()

        # ждём сигнала от потока: либо иконка показалась, либо упала.
        ok = started.wait(timeout=4.0) and not failed.is_set()
        if not ok:
            log.warning("tray icon did not signal readiness")
            self._icon = None
            return False
        self._running = True
        return True

    def _build_menu(self, pystray):
        MenuItem = pystray.MenuItem
        Menu = pystray.Menu

        # ── строка статуса (некликабельная) ─────────────────────────
        def _status_label(_item) -> str:
            try:
                on = self._is_on()
                cfg = self._cfg()
                app_mode = str(cfg.get("app_mode", "dpi"))
                state = "включён" if on else "выключен"
                if app_mode == "vpn":
                    return f"VPN {state}"
                strategy = str(cfg.get("zapret_strategy", "") or "")
                if strategy.lower() == "auto":
                    short = "Авто"
                    auto = str(cfg.get("zapret_strategy_auto_result", "") or "")
                    if auto:
                        short = f"Авто · {self._strategy_short(auto)}"
                else:
                    short = self._strategy_short(strategy)
                return f"Обход {state} · {short}" if short else f"Обход {state}"
            except Exception:
                return "EXDPI"

        def _toggle_label(_item) -> str:
            try:
                return "Выключить" if self._is_on() else "Включить"
            except Exception:
                return "Переключить"

        def _safe(cb: Optional[Callable], *args) -> None:
            if cb is None:
                return
            try:
                cb(*args)
            except Exception:
                log.exception("tray callback failed")

        # ── submenu: стратегия ──────────────────────────────────────
        def _strategy_items() -> List:
            items: List = []
            cfg = self._cfg()
            current = str(cfg.get("zapret_strategy", "") or "")

            def _make(strategy_id: str, label: str):
                return MenuItem(
                    label,
                    lambda _i, _it, s=strategy_id: _safe(self._on_strategy, s),
                    checked=lambda _it, s=strategy_id: (
                        str(self._cfg().get("zapret_strategy", "")) == s
                    ),
                    radio=True,
                )

            items.append(_make("auto", "Авто (подбор лучшей)"))
            try:
                from .zapret_runner import list_strategies
                strategies = list_strategies()
            except Exception:
                strategies = [current] if current and current != "auto" else []
            for s in strategies:
                items.append(_make(s, self._strategy_short(s)))
            return items

        def _mode_items() -> List:
            items: List = []
            for mode_id, label in _MODE_LABELS:
                items.append(MenuItem(
                    label,
                    lambda _i, _it, m=mode_id: _safe(self._on_mode, m),
                    checked=lambda _it, m=mode_id: (
                        str(self._cfg().get("game_mode", "normal")) == m
                    ),
                    radio=True,
                ))
            return items

        def _app_mode_items() -> List:
            items: List = []
            for mode_id, label in _APP_MODE_LABELS:
                items.append(MenuItem(
                    label,
                    lambda _i, _it, m=mode_id: _safe(self._on_app_mode, m),
                    checked=lambda _it, m=mode_id: (
                        str(self._cfg().get("app_mode", "dpi")) == m
                    ),
                    radio=True,
                ))
            return items

        # ── видимость пунктов, специфичных для режима ────────────────
        def _is_dpi_mode(_it) -> bool:
            return str(self._cfg().get("app_mode", "dpi")) != "vpn"

        def _is_vpn_mode(_it) -> bool:
            return str(self._cfg().get("app_mode", "dpi")) == "vpn"

        parts: List = [
            MenuItem(_status_label, None, enabled=False),
            Menu.SEPARATOR,
            MenuItem("Открыть EXDPI", lambda _i, _it: _safe(self._on_show), default=True),
            MenuItem(_toggle_label, lambda _i, _it: _safe(self._on_toggle)),
        ]
        if self._on_app_mode is not None:
            parts.append(MenuItem("Приложение", Menu(*_app_mode_items())))
        if self._on_strategy is not None:
            parts.append(MenuItem(
                "Стратегия", Menu(*_strategy_items()), visible=_is_dpi_mode,
            ))
        if self._on_mode is not None:
            parts.append(MenuItem(
                "Режим", Menu(*_mode_items()), visible=_is_dpi_mode,
            ))
        extra: List = []
        if self._on_dpitest is not None:
            extra.append(MenuItem(
                "Проверить обход", lambda _i, _it: _safe(self._on_dpitest),
                visible=_is_dpi_mode,
            ))
        if self._on_logs is not None:
            extra.append(MenuItem("Папка с логами", lambda _i, _it: _safe(self._on_logs)))
        if self._on_settings is not None:
            extra.append(MenuItem("Настройки", lambda _i, _it: _safe(self._on_settings)))
        if extra:
            parts.append(Menu.SEPARATOR)
            parts.extend(extra)
        parts.append(Menu.SEPARATOR)

        def _click_quit(icon, _item):
            _safe(self._on_quit)
            try:
                icon.stop()
            except Exception:
                pass

        parts.append(MenuItem("Выход", _click_quit))
        return Menu(*parts)

    # ── runtime updates ──────────────────────────────────────────────

    def update_state(self) -> None:
        """Перерисовать меню и иконку после смены состояния/настроек."""
        if not self._icon:
            return
        try:
            on = self._is_on()
            if on != self._last_on and self._img_on is not None:
                self._icon.icon = self._img_on if on else self._img_off  # type: ignore[union-attr]
                self._last_on = on
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
