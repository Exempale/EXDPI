"""Главное окно: минималистичный экран с большим переключателем."""
from __future__ import annotations

import logging
import sys
import threading
import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional

from . import __version__, autostart, easter, i18n, logs, notify, paths, singbox_config
from .config import save as save_config
from .controller import Controller
from .theme import THEME, apply_theme, available_themes
from .tray import TrayController
from .ui_dpitest import DpiTestDialog
from .ui_settings import SettingsWindow
from .ui_tg_guide import TgVcGuideDialog
from .ui_wizard import FirstRunWizard
from .updater import UpdateDialog, check_async, snooze_for_three_days
from .widgets import (
    AnimatedToggle,
    AppModeSwitch,
    IconButton,
    ServerListBox,
    StatusDot,
)

log = logging.getLogger("dpibypass.ui")


class App(tk.Tk):
    WIDTH = 400
    HEIGHT = 400
    MIN_WIDTH = 400
    MIN_HEIGHT = 400

    def __init__(self) -> None:
        super().__init__()

        # Показывать полный traceback необработанных ошибок Tk-колбэков в
        # копируемом окне: под PyInstaller (console=False) любое исключение в
        # колбэке (открытие настроек, клики и т.п.) иначе пропадает молча.
        self.report_callback_exception = self._report_callback_exception

        self.ctl = Controller()
        i18n.set_language(str(self.ctl.cfg.get("language", "auto")))
        self.ctl.bind(on_state=self._on_state, on_error=self._on_error)

        self._error_text: Optional[str] = None
        self._after_jobs: list[str] = []
        self._tray: Optional[TrayController] = None
        self._quitting = False
        # список серверов из последней разобранной подписки (http/https);
        # для прямой ссылки vless/ss — пусто, поле "локация" скрыто.
        self._vpn_servers: List[Dict[str, str]] = []

        # запуск свёрнутым: прячем окно СРАЗУ, до первой отрисовки, чтобы оно
        # не успело мелькнуть на экране (--minimized в argv или настройка).
        self._start_minimized = bool(self.ctl.cfg.get("start_minimized", False)) or (
            "--minimized" in sys.argv[1:]
        )

        self.title("EXDPI")
        self.configure(bg=THEME.bg)
        self.resizable(True, True)
        if self._start_minimized:
            try:
                self.withdraw()
            except Exception:
                pass
        # размер/минимум окна зависят от режима (DPI компактный, VPN выше)
        self._apply_mode_geometry()

        # Иконка окна (тайтлбар + панель задач): штатный Tk-путь
        # (iconbitmap/iconphoto) плюс надёжный WinAPI-фоллбэк — см. _apply_window_icon.
        self._apply_window_icon()

        # удалим стандартное меню
        try:
            self.option_add("*Menu.background", THEME.card)
            self.option_add("*Menu.foreground", THEME.text_primary)
        except Exception:
            pass

        self._build()
        self._refresh_status_text()
        self._schedule_stats_refresh()
        self._schedule_update_check()

        # синхронизируем реестр Windows с конфигом (на случай, если
        # пользователь руками удалил запись или путь к exe изменился)
        try:
            autostart.apply(bool(self.ctl.cfg.get("autostart_with_windows", False)))
        except Exception:
            log.exception("autostart sync failed")

        # уведомления Windows — по настройке (ставим ДО трея, чтобы тосты
        # сразу шли через иконку трея)
        notify.set_enabled(bool(self.ctl.cfg.get("notifications_enabled", True)))

        # tray-иконка: нужна для сворачивания в трей, запуска свёрнутым и
        # для нативных тостов-уведомлений (Shell_NotifyIcon). Поднимаем, если
        # включена хотя бы одна из этих функций.
        if (
            self.ctl.cfg.get("minimize_to_tray", True)
            or self._start_minimized
            or self.ctl.cfg.get("notifications_enabled", True)
        ):
            self._init_tray()

        # запуск свёрнутым: окно уже withdraw()-нуто в начале __init__.
        # Если трей не поднялся — окно потерялось бы, поэтому показываем его
        # свёрнутым в панель задач (iconify) как запасной вариант.
        if self._start_minimized:
            if self._tray is None:
                try:
                    self.deiconify()
                    self.iconify()
                except Exception:
                    pass

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Watchdog + горячие клавиши + мониторинг сервисов
        self._init_services()

        # мастер первого запуска — один раз
        if not bool(self.ctl.cfg.get("wizard_done", False)):
            self.after(400, self._open_wizard)
        # автовключение обхода при старте (пока мастер не пройден — не дёргаем)
        elif bool(self.ctl.cfg.get("start_enabled", False)):
            self.after(1500, self._auto_enable_bypass)

    # ── фоновые сервисы ──────────────────────────────────────────────
    def _init_services(self) -> None:
        from . import healthcheck as healthcheck_mod
        from . import hotkeys as hotkeys_mod
        from . import strategy_cloud as strategy_cloud_mod
        from . import watchdog as watchdog_mod

        try:
            self._watchdog = watchdog_mod.Watchdog(self.ctl)
            self._watchdog.start()
        except Exception:
            log.exception("watchdog start failed")
        try:
            if sys.platform == "win32":
                self._hotkeys = hotkeys_mod.HotkeyManager(
                    self.ctl.cfg,
                    self._on_hotkey_toggle,
                    on_showhide=self._on_hotkey_showhide)
                self._hotkeys.start()
        except Exception:
            log.exception("hotkeys start failed")
        # облачные стратегии — в фоне, не блокируя UI
        try:
            if strategy_cloud_mod.should_run(self.ctl.cfg):
                self.after(3000, lambda: strategy_cloud_mod.run_async(
                    self.ctl.cfg, self._on_strategy_cloud_done))
        except Exception:
            log.exception("strategy cloud start failed")
        # мониторинг сервисов (health-check + автопереключение)
        try:
            self._health = healthcheck_mod.HealthChecker(
                self.ctl,
                on_status=self._on_health_status,
                on_notify=lambda msg: notify.send(msg))
            self._health.start()
        except Exception:
            log.exception("healthcheck start failed")

    def _auto_enable_bypass(self) -> None:
        """Включить обход при старте приложения (настройка start_enabled).

        Эквивалент клика по большому тумблеру: состояние тумблера, полный
        _on_toggle(True) со всеми проверками (VPN-ссылка, busy и т.д.).
        """
        try:
            if self.ctl.is_on() or self.ctl.is_target_on():
                return
            self.toggle.set(True, animate=False)
            self._on_toggle(True)
        except Exception:
            log.exception("auto enable bypass failed")

    def _on_hotkey_toggle(self) -> None:
        """Горячая клавиша: переключаем ON/OFF (с маршаллингом в UI-поток)."""
        try:
            self.after(0, self._tray_toggle)
        except Exception:
            log.exception("hotkey toggle marshall failed")

    def _on_hotkey_showhide(self) -> None:
        """Горячая клавиша: показать/скрыть окно (с маршаллингом в UI-поток)."""
        try:
            self.after(0, self._toggle_window_visible)
        except Exception:
            log.exception("hotkey showhide marshall failed")

    def _toggle_window_visible(self) -> None:
        """Скрыть окно, если оно видно, и показать, если скрыто."""
        visible = True
        hwnd = self._win32_hwnd()
        if hwnd:
            try:
                import ctypes
                visible = bool(ctypes.windll.user32.IsWindowVisible(hwnd))
            except Exception:
                visible = True
        if visible:
            self._win32_hide()
        else:
            self._win32_show()

    def _on_strategy_cloud_done(self, message: str) -> None:
        if not message:
            return
        try:
            # вызывается из фонового потока — UI трогаем только через after
            self.after(0, lambda: self._flash_hint(message))
            notify.send(message)
        except Exception:
            log.exception("strategy cloud notify failed")

    # ── мониторинг сервисов (health-check) ───────────────────────────
    def _make_health_row(self, parent) -> None:
        """Строка индикаторов YouTube/Discord/ChatGPT в главном окне."""
        from . import healthcheck as healthcheck_mod
        self._health_dots = {}
        self._health_row = None
        if not bool(self.ctl.cfg.get("hc_enabled", True)):
            return
        row = tk.Frame(parent, bg=THEME.bg)
        row.pack(pady=(8, 0))
        self._health_row = row
        tk.Label(row, text=i18n.t("main.monitoring"), fg=THEME.text_muted, bg=THEME.bg,
                 font=(THEME.font_ui, 8)).pack(side="left", padx=(0, 8))
        for name, _h, _p, _s in healthcheck_mod.SERVICES:
            cell = tk.Frame(row, bg=THEME.bg)
            cell.pack(side="left", padx=6)
            dot = tk.Canvas(cell, width=8, height=8, bg=THEME.bg,
                            highlightthickness=0, bd=0)
            dot.pack(anchor="center")
            dot.create_oval(1, 1, 7, 7, fill=THEME.border, outline="")
            self._health_dots[name] = dot
            tk.Label(cell, text=name, fg=THEME.text_muted, bg=THEME.bg,
                     font=(THEME.font_ui, 8)).pack()

    def _on_health_status(self, results, network_ok) -> None:
        """Колбэк из потока health-check — маршаллим в UI-поток."""
        try:
            self.after(0, lambda: self._render_health(results, network_ok))
        except Exception:
            log.exception("health status marshall failed")

    def _render_health(self, results, network_ok) -> None:
        dots = getattr(self, "_health_dots", None)
        if not dots:
            return
        for name, dot in dots.items():
            ok = results.get(name)
            if ok is None:
                color = THEME.border
            elif ok:
                color = THEME.track_on
            else:
                color = THEME.text_muted if not network_ok else THEME.danger
            try:
                dot.delete("all")
                dot.create_oval(1, 1, 7, 7, fill=color, outline="")
            except Exception:
                pass

    # ── layout ───────────────────────────────────────────────────────
    def _center_on_screen(self) -> None:
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = (sw - self.WIDTH) // 2
        y = (sh - self.HEIGHT) // 2 - 40
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{max(0, x)}+{max(0, y)}")

    # ── размеры окна под режим (VPN шире/выше — там список серверов,
    #    поле ссылки и баннер; DPI компактный) ──────────────────────────
    def _apply_mode_geometry(self) -> None:
        """Подобрать размер/минимум окна под текущий режим приложения.

        VPN-экран несёт список серверов и поле ссылки, поэтому ему нужно
        больше высоты, чем компактному DPI-экрану. Высота ограничивается
        высотой экрана, чтобы окно не уезжало за край на ноутбуках.
        """
        if self.ctl.is_vpn:
            w, h, min_w, min_h = 640, 620, 560, 460
        else:
            w, h, min_w, min_h = 400, 440, 400, 420
        try:
            sh = self.winfo_screenheight()
            if h > sh - 80:
                h = max(min_h, sh - 80)
        except Exception:
            pass
        self.WIDTH, self.HEIGHT = w, h
        try:
            self.minsize(min_w, min_h)
        except Exception:
            pass
        self._center_on_screen()

    def _build(self) -> None:
        outer = tk.Frame(self, bg=THEME.bg, padx=22, pady=18)
        outer.pack(fill="both", expand=True)

        # ── header ───────────────────────────────────────────────────
        header = tk.Frame(outer, bg=THEME.bg)
        header.pack(fill="x")

        # иконки справа — пакуем ПЕРВЫМИ, чтобы гарантированно влезали
        # в строку, даже если заголовок слева разрастётся.
        IconButton(
            header, glyph="gear", size=30,
            on_click=self._open_settings, tooltip="Настройки",
        ).pack(side="right", padx=(8, 0), pady=(2, 0))
        IconButton(
            header, glyph="theme", size=30,
            on_click=self._cycle_theme,
            tooltip="Переключить тему",
        ).pack(side="right", padx=(8, 0), pady=(2, 0))

        # переключатель DPI/VPN только на Windows: на macOS приложение
        # целиком работает в VPN-режиме (WinDivert существует лишь там)
        if sys.platform == "win32":
            self.mode_switch = AppModeSwitch(
                header, value=str(self.ctl.cfg.get("app_mode", "dpi")),
                on_change=self._on_app_mode_change,
            )
            self.mode_switch.pack(side="right", padx=(8, 8), pady=(2, 0))
        else:
            self.mode_switch = None

        head_left = tk.Frame(header, bg=THEME.bg)
        head_left.pack(side="left", fill="x", expand=True)
        tk.Label(
            head_left, text="ОБХОД",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 8, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            head_left, text="EXDPI",
            fg=THEME.text_primary, bg=THEME.bg,
            font=(THEME.font_ui, 14, "bold"),
            anchor="w",
        ).pack(anchor="w")

        # ── divider ──────────────────────────────────────────────────
        div = tk.Frame(outer, bg=THEME.border, height=1)
        div.pack(fill="x", pady=(14, 0))

        # ── center area: DPI-режим или VPN-режим ───────────────────────
        center = tk.Frame(outer, bg=THEME.bg)
        center.pack(expand=True, fill="both")

        if self.ctl.is_vpn:
            self._build_vpn_view(center)
        else:
            self._build_dpi_view(center)

        # ── footer ──────────────────────────────────────────────────
        footer = tk.Frame(outer, bg=THEME.bg)
        footer.pack(side="bottom", fill="x", pady=(8, 0))

        tk.Label(
            footer, text="автор · Exempale",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 9, "bold"),
        ).pack(side="left")
        # версия — она же скрытая пасхалка: 5 кликов подряд открывают
        # прикольную картинку :D
        self._egg_clicks = 0
        ver_lbl = tk.Label(
            footer, text=f"EXDPI v{__version__}",
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 8), cursor="hand2",
        )
        ver_lbl.pack(side="right")
        ver_lbl.bind("<Button-1>", lambda _e: self._on_egg_click())

    def _build_dpi_view(self, center: tk.Frame) -> None:
        toggle_box = tk.Frame(center, bg=THEME.bg)
        toggle_box.pack(expand=True)

        # spacer top
        tk.Frame(toggle_box, bg=THEME.bg, height=18).pack()

        self.toggle = AnimatedToggle(toggle_box, on_change=self._on_toggle)
        self.toggle.pack(pady=(0, 16))

        # status row: dot + label
        status_row = tk.Frame(toggle_box, bg=THEME.bg)
        status_row.pack()
        self.dot = StatusDot(status_row)
        self.dot.pack(side="left", padx=(0, 8))
        self.status_lbl = tk.Label(
            status_row, text=i18n.t("main.off"),
            fg=THEME.text_primary, bg=THEME.bg,
            font=(THEME.font_ui, 16, "bold"),
        )
        self.status_lbl.pack(side="left")

        # proxy info row: "mtproto · 127.0.0.1:1443  📋"
        info_row = tk.Frame(toggle_box, bg=THEME.bg)
        info_row.pack(pady=(8, 0))
        self.info_lbl = tk.Label(
            info_row, text="—",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 10),
        )
        self.info_lbl.pack(side="left")
        self.copy_btn = IconButton(
            info_row, glyph="copy", size=20,
            on_click=self._copy_link, tooltip="Скопировать MTProto-ссылку",
        )
        self.copy_btn.pack(side="left", padx=(8, 0))

        # connections / hint label
        self.hint_lbl = tk.Label(
            toggle_box, text="нет соединений",
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 9),
            wraplength=360, justify="center",
        )
        self.hint_lbl.pack(pady=(6, 0))

        self._make_health_row(toggle_box)

        # diagnostic link — открывает DPI-тест (TLS-handshake к набору хостов)
        self.diag_lbl = tk.Label(
            toggle_box, text=i18n.t("main.test_bypass"),
            fg=THEME.accent_dim, bg=THEME.bg,
            font=(THEME.font_ui, 9, "underline"),
            cursor="hand2",
        )
        self.diag_lbl.pack(pady=(4, 0))
        self.diag_lbl.bind("<Button-1>", lambda _e: self._open_dpitest())

        # ссылка на справку по Telegram VC прокси
        self.tg_lbl = tk.Label(
            toggle_box, text="подключить прокси в Telegram",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 9, "underline"),
            cursor="hand2",
        )
        self.tg_lbl.pack(pady=(2, 0))
        self.tg_lbl.bind("<Button-1>", lambda _e: self._open_tg_guide())

        # подпись-переключатель текущего режима zapret — обычный/гейминг.
        # Клик по ней мгновенно меняет режим (и перезапускает обход, если он
        # включён) — это «плашка» режима прямо на главном экране.
        self.mode_lbl = tk.Label(
            toggle_box, text="",
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 8, "bold"),
            cursor="hand2",
        )
        self.mode_lbl.pack(pady=(6, 0))
        self.mode_lbl.bind("<Button-1>", lambda _e: self._cycle_game_mode())

    def _build_vpn_view(self, center: tk.Frame) -> None:
        toggle_box = tk.Frame(center, bg=THEME.bg)
        toggle_box.pack(expand=True, fill="both")

        tk.Frame(toggle_box, bg=THEME.bg, height=10).pack()

        self._vpn_sub_job: Optional[str] = None

        uri_field = tk.Frame(toggle_box, bg=THEME.bg)
        uri_field.pack(fill="x", pady=(0, 10))
        uri_head = tk.Frame(uri_field, bg=THEME.bg)
        uri_head.pack(fill="x")
        tk.Label(
            uri_head, text="VPN-ССЫЛКА (vless://, ss://, vmess://, trojan://, "
                             "hysteria2://, tuic://, wireguard:// или подписка http/https)",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 8, "bold"), anchor="w", wraplength=440,
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        wg_btn = tk.Label(uri_head, text="импорт .conf (WireGuard)",
                          fg=THEME.accent_dim, bg=THEME.bg,
                          font=(THEME.font_ui, 8, "underline"), cursor="hand2")
        wg_btn.pack(side="right")
        wg_btn.bind("<Button-1>", lambda _e: self._on_import_wg_conf())
        initial_uri = str(self.ctl.cfg.get("vpn_sub_url") or self.ctl.cfg.get("vpn_uri") or "")
        self.vpn_uri_var = tk.StringVar(value=initial_uri)
        self.vpn_uri_entry = tk.Entry(
            uri_field,
            textvariable=self.vpn_uri_var,
            bg=THEME.card, fg=THEME.text_primary,
            insertbackground=THEME.accent,
            relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground=THEME.border,
            highlightcolor=THEME.accent_dim,
            font=(THEME.font_ui, 10),
        )
        self.vpn_uri_entry.pack(fill="x", ipady=6, pady=(4, 0))
        self.vpn_uri_var.trace_add("write", lambda *_a: self._on_vpn_uri_change())
        # Ctrl+V из tk.Entry обычно работает через виртуальное событие
        # <<Paste>>, но на русской раскладке клавиатуры keysym для V может
        # отличаться от латинского "v" — тогда стандартный bind не срабатывает.
        # Проверяем по физическому keycode (не зависит от раскладки).
        self.vpn_uri_entry.bind("<Key>", self._on_vpn_uri_keypress)

        self._vpn_uri_field = uri_field

        self.server_list = ServerListBox(
            toggle_box,
            on_select=self._on_location_selected,
            on_refresh=self._on_refresh_servers,
            on_ping=self._on_ping_servers,
            height=150,
        )
        self.server_list.pack(fill="x", pady=(0, 10))

        self.toggle = AnimatedToggle(toggle_box, on_change=self._on_toggle)
        self.toggle.pack(pady=(6, 16))

        status_row = tk.Frame(toggle_box, bg=THEME.bg)
        status_row.pack()
        self.dot = StatusDot(status_row)
        self.dot.pack(side="left", padx=(0, 8))
        self.status_lbl = tk.Label(
            status_row, text=i18n.t("main.off"),
            fg=THEME.text_primary, bg=THEME.bg,
            font=(THEME.font_ui, 16, "bold"),
        )
        self.status_lbl.pack(side="left")

        self.hint_lbl = tk.Label(
            toggle_box, text=i18n.t("main.off_vpn"),
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 9),
            wraplength=360, justify="center",
        )
        self.hint_lbl.pack(pady=(6, 0))

        self._make_health_row(toggle_box)

        self._refresh_server_list_from_cfg()
        sub_url = str(self.ctl.cfg.get("vpn_sub_url", "")).strip()
        if sub_url and not self._vpn_servers:
            self._schedule_vpn_link_resolve(delay=50)

    def _on_import_wg_conf(self) -> None:
        """Импорт WireGuard/AmneziaWG конфига из .conf файла."""
        from tkinter import filedialog
        from . import wireguard as wgmod
        path = filedialog.askopenfilename(
            parent=self, title="Выберите WireGuard .conf",
            filetypes=[("WireGuard конфиг", "*.conf"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        try:
            text = open(path, "r", encoding="utf-8", errors="replace").read()
            wg = wgmod.parse_wireguard_conf(text)
        except Exception as exc:
            log.exception("wg conf import failed")
            try:
                self.hint_lbl.configure(
                    text=f"Не удалось импортировать .conf: {exc}",
                    fg=THEME.danger)
            except Exception:
                pass
            return
        self.ctl.cfg["vpn_wg_conf"] = text
        self.ctl.cfg["vpn_uri"] = "wgconf://local"
        self.ctl.save()
        self.vpn_uri_var.set("wgconf://local")
        try:
            msg = f"Импортирован {wgmod.summary(wg)}"
            if wg.get("awg") and not wgmod.SUPPORTS_AWG:
                msg += (" · обфускация AmneziaWG движком не поддерживается — "
                        "подключение как обычный WireGuard")
            self.hint_lbl.configure(text=msg, fg=THEME.accent_dim)
        except Exception:
            pass

    def _on_vpn_uri_keypress(self, event: "tk.Event") -> Optional[str]:
        """Явный Ctrl+V, независимый от раскладки клавиатуры.

        ``keycode`` — физический код клавиши (86 = "V" на стандартной
        QWERTY-раскладке) и не зависит от текущего языка ввода, в отличие
        от ``keysym``, который на кириллической раскладке может прислать
        совсем другой символ и не сработать со стандартным Control-V.
        """
        ctrl = bool(event.state & 0x0004)
        if ctrl and event.keycode == 86:
            try:
                clip = self.clipboard_get()
            except Exception:
                return None
            try:
                self.vpn_uri_entry.delete(0, tk.END)
                self.vpn_uri_entry.insert(0, clip.strip())
            except Exception:
                pass
            return "break"
        return None

    def _on_vpn_uri_change(self) -> None:
        raw = self.vpn_uri_var.get().strip()
        if singbox_config.is_subscription_url(raw):
            # подписка — не пишем в vpn_uri прямо, ждём фетча/разбора
            self.ctl.cfg["vpn_sub_url"] = raw
            self.ctl.save()
            self._schedule_vpn_link_resolve()
            return

        if self._vpn_sub_job is not None:
            try:
                self.after_cancel(self._vpn_sub_job)
            except Exception:
                pass
            self._vpn_sub_job = None
        self.ctl.cfg["vpn_uri"] = raw
        self.ctl.cfg["vpn_sub_url"] = ""
        self.ctl.cfg["vpn_sub_tag"] = ""
        self.ctl.save()
        self._refresh_server_list_from_cfg()

    def _schedule_vpn_link_resolve(self, delay: int = 700) -> None:
        if self._vpn_sub_job is not None:
            try:
                self.after_cancel(self._vpn_sub_job)
            except Exception:
                pass
        self._vpn_sub_job = self.after(delay, self._resolve_vpn_link)

    def _resolve_vpn_link(self) -> None:
        """Скачать и разобрать подписку в фоне, не блокируя UI."""
        self._vpn_sub_job = None
        url = str(self.ctl.cfg.get("vpn_sub_url", "")).strip()
        if not url:
            return
        try:
            self.hint_lbl.configure(text="проверка подписки…", fg=THEME.text_muted)
            self.server_list.set_refreshing(True)
        except Exception:
            pass

        def _work() -> None:
            try:
                servers = singbox_config.list_servers(url)
                err = None
            except Exception as exc:
                servers = []
                err = str(exc)
            self.after(0, lambda: self._apply_resolved_servers(url, servers, err))

        threading.Thread(target=_work, daemon=True, name="vpn-sub-fetch").start()

    def _apply_resolved_servers(
        self, url: str, servers: List[Dict[str, str]], err: Optional[str]
    ) -> None:
        try:
            self.server_list.set_refreshing(False)
        except Exception:
            pass
        # пока шёл фетч, пользователь мог поменять поле — тогда результат
        # уже неактуален, применять его не нужно.
        if str(self.ctl.cfg.get("vpn_sub_url", "")).strip() != url:
            return
        if err or not servers:
            self._vpn_servers = []
            self._update_location_picker()
            try:
                self.hint_lbl.configure(
                    text=f"подписка: {err or 'нет серверов'}", fg=THEME.danger_dim
                )
            except Exception:
                pass
            return

        self._vpn_servers = servers
        prev_tag = str(self.ctl.cfg.get("vpn_sub_tag", ""))
        chosen = next((s for s in servers if s["tag"] == prev_tag), servers[0])
        self.ctl.cfg["vpn_uri"] = chosen["uri"]
        self.ctl.cfg["vpn_sub_tag"] = chosen["tag"]
        self.ctl.save()
        self._update_location_picker()
        try:
            self.hint_lbl.configure(
                text=f"подписка: найдено {len(servers)} серверов", fg=THEME.text_muted
            )
        except Exception:
            pass

    def _refresh_server_list_from_cfg(self) -> None:
        """Синхронизировать список серверов с конфигом без похода в сеть.

        Для прямой ссылки (не подписки) строим список из одного элемента —
        так пользователь может замерить пинг и увидеть флаг/тег даже без
        подписки. Для подписки список заполнит фоновый фетч (см.
        ``_resolve_vpn_link``) — здесь только не даём экрану остаться пустым,
        если результат уже был закэширован в ``self._vpn_servers``.
        """
        sub_url = str(self.ctl.cfg.get("vpn_sub_url", "")).strip()
        if sub_url:
            self._update_location_picker()
            return

        uri = str(self.ctl.cfg.get("vpn_uri", "")).strip()
        if uri:
            try:
                parsed = singbox_config.parse_uri(uri)
                self._vpn_servers = [{
                    "tag": str(parsed.get("tag") or "server"),
                    "uri": uri,
                    "type": parsed.get("type", ""),
                    "server": parsed.get("server", ""),
                    "server_port": parsed.get("server_port", 0),
                }]
            except Exception:
                self._vpn_servers = []
        else:
            self._vpn_servers = []
        self._update_location_picker()

    def _update_location_picker(self) -> None:
        try:
            lst = self.server_list
        except AttributeError:
            return
        current_tag = str(self.ctl.cfg.get("vpn_sub_tag", ""))
        tags = [s["tag"] for s in self._vpn_servers]
        selected = current_tag if current_tag in tags else (tags[0] if tags else "")
        lst.set_servers(self._vpn_servers, selected_tag=selected)

    def _on_location_selected(self, tag: str) -> None:
        match = next((s for s in self._vpn_servers if s["tag"] == tag), None)
        if not match:
            return
        self.ctl.cfg["vpn_uri"] = match["uri"]
        self.ctl.cfg["vpn_sub_tag"] = match["tag"]
        self.ctl.save()
        if self.ctl.is_on():
            def _restart():
                try:
                    self.ctl.restart_with_new_config()
                except Exception:
                    log.exception("vpn location restart failed")
                finally:
                    self.after(0, self._refresh_status_text)
            threading.Thread(target=_restart, daemon=True, name="vpn-loc-restart").start()

    def _on_refresh_servers(self) -> None:
        """Кнопка «обновить» в списке серверов: перечитать подписку с сервера."""
        sub_url = str(self.ctl.cfg.get("vpn_sub_url", "")).strip()
        if not sub_url:
            self._refresh_server_list_from_cfg()
            return
        self._schedule_vpn_link_resolve(delay=0)

    def _on_ping_servers(self) -> None:
        """Кнопка «пинг»: TCP-connect задержка до каждого сервера списка.

        Замеры идут параллельно в пуле потоков (не в UI-потоке — сокет с
        таймаутом иначе подвесил бы окно на несколько секунд при большой
        подписке), результаты возвращаются в UI через ``self.after``.
        """
        servers = list(self._vpn_servers)
        if not servers:
            return
        try:
            self.server_list.set_pinging(True)
        except Exception:
            pass

        results: Dict[str, int] = {}

        def _ping_one_collect(srv: Dict[str, str]) -> None:
            host = str(srv.get("server", ""))
            port = srv.get("server_port", 0)
            try:
                ms = singbox_config.ping_server(host, int(port)) if host and port else -1
            except Exception:
                ms = -1
            results[srv["tag"]] = ms
            self.after(0, lambda t=srv["tag"], m=ms: self.server_list.set_ping(t, m))

        def _work() -> None:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(_ping_one_collect, servers))
            self.after(0, lambda: self.server_list.set_pinging(False))
            if bool(self.ctl.cfg.get("vpn_autoselect_fastest", False)):
                alive = {t: m for t, m in results.items() if m >= 0}
                if alive:
                    best = min(alive, key=alive.get)
                    self.after(0, lambda t=best: self._autoselect_best(t))

        threading.Thread(target=_work, daemon=True, name="vpn-ping").start()

    def _autoselect_best(self, tag: str) -> None:
        """Выбрать самый быстрый сервер (по последнему замеру пинга)."""
        try:
            self.server_list.set_selected(tag)
        except Exception:
            pass
        self._on_location_selected(tag)
        try:
            self._flash_hint("выбран самый быстрый сервер")
        except Exception:
            pass

    def _on_app_mode_change(self, mode: str) -> None:
        if str(self.ctl.cfg.get("app_mode", "dpi")) == mode:
            return
        was_on = self.ctl.is_on()
        self._error_text = None
        self.ctl.cfg["app_mode"] = mode
        self.ctl.save()

        def _restart():
            try:
                if was_on:
                    self.ctl.restart_with_new_config()
            except Exception:
                log.exception("app mode restart failed")
            finally:
                self.after(0, self._rebuild_ui)

        if was_on:
            threading.Thread(target=_restart, daemon=True, name="mode-switch-restart").start()
        else:
            self._rebuild_ui()

    # ── footer / пасхалка ─────────────────────────────────────────────
    def _on_egg_click(self) -> None:
        """5 кликов по версии в футере → открыть картинку-пасхалку."""
        self._egg_clicks += 1
        if self._egg_clicks >= 5:
            self._egg_clicks = 0
            try:
                easter.show_easter_egg(self)
            except Exception:
                log.exception("easter egg failed")

    # ── status / refresh ─────────────────────────────────────────────
    def _refresh_status_text(self) -> None:
        cfg = self.ctl.cfg
        if not self.ctl.is_vpn:
            host = cfg.get("proxy_host", "127.0.0.1")
            port = cfg.get("proxy_port", 1443)
            try:
                self.info_lbl.configure(text=f"mtproto · {host}:{port}")
            except Exception:
                pass

            mode = str(cfg.get("game_mode", "normal"))
            mode_name = i18n.t("main.mode_gaming") if mode == "gaming" else i18n.t("main.mode_normal")
            mode_text = i18n.t("main.mode_change", m=mode_name)
            try:
                self.mode_lbl.configure(text=mode_text)
            except Exception:
                pass

        is_on = self.ctl.is_on()
        self.toggle.set(is_on, animate=False)
        if self._error_text:
            self.status_lbl.configure(text="Ошибка", fg=THEME.danger)
            self.dot.set_color(THEME.danger)
            self.hint_lbl.configure(text=self._error_text, fg=THEME.danger_dim)
        elif is_on:
            self.status_lbl.configure(text=i18n.t("main.on"), fg=THEME.text_primary)
            self.dot.set_color(THEME.accent)
            if self.ctl.is_vpn:
                self.hint_lbl.configure(text="VPN: подключён", fg=THEME.text_muted)
        else:
            self.status_lbl.configure(text=i18n.t("main.off"), fg=THEME.text_primary)
            self.dot.set_color(THEME.danger)
            if self.ctl.is_vpn:
                self.hint_lbl.configure(text=i18n.t("main.off_vpn"), fg=THEME.text_muted)

        if self._tray is not None:
            try:
                self._tray.update_state()
            except Exception:
                pass

    def _schedule_stats_refresh(self) -> None:
        if not self.ctl.is_vpn and not self._error_text:
            try:
                stats = self.ctl.proxy.stats_snapshot() if self.ctl.proxy.is_running else None
            except Exception:
                stats = None
            if stats is None:
                self.hint_lbl.configure(text="нет соединений", fg=THEME.text_muted)
            else:
                active = stats["active"]
                total = stats["total"]
                if active == 0 and total == 0:
                    txt = "нет соединений"
                elif active == 0:
                    txt = f"всего: {total}"
                else:
                    txt = f"{active} активн. · всего {total}"
                self.hint_lbl.configure(text=txt, fg=THEME.text_muted)

        job = self.after(1500, self._schedule_stats_refresh)
        self._after_jobs.append(job)

    # ── controller callbacks (UI thread bounce) ──────────────────────
    def _on_state(self, _on: bool) -> None:
        self.after(0, self._refresh_status_text)

    def _on_error(self, msg: str) -> None:
        def _apply():
            self._error_text = str(msg)
            self._refresh_status_text()
        self.after(0, _apply)
        try:
            notify.send(f"Ошибка: {msg[:120]}")
        except Exception:
            log.exception("error toast failed")

    # ── interactions ─────────────────────────────────────────────────
    def _enabled_notify_text(self) -> str:
        """Текст уведомления об успешном включении (с указанием режима)."""
        mode = str(self.ctl.cfg.get("game_mode", "normal"))
        mode_ru = "гейминг" if mode == "gaming" else "обычный"
        return i18n.t("main.status_on_mode", m=mode_ru)

    def _on_toggle(self, value: bool) -> None:
        self._error_text = None
        self.toggle.set_busy(True)
        self.status_lbl.configure(text="…", fg=THEME.text_secondary)

        # Pro: перед включением VPN — авто-пинг всех локаций и выбор лучшей
        if value and self._pro_should_preping():
            self.status_lbl.configure(text=i18n.t("main.best_server"), fg=THEME.text_secondary)
            try:
                self.server_list.set_pinging(True)
            except Exception:
                pass
            threading.Thread(target=self._preping_work, daemon=True,
                             name="vpn-preping").start()
            return

        threading.Thread(target=self._toggle_work, args=(value,),
                         daemon=True, name="toggle-work").start()

    def _toggle_work(self, value: bool) -> None:
        try:
            if value:
                self.ctl.start()
            else:
                self.ctl.stop()
        except Exception:
            log.exception("toggle work failed")
        finally:
            self.after(0, lambda: self._after_toggle(value))

    # ── Pro: автовыбор лучшего пинга ─────────────────────────────────
    def _pro_should_preping(self) -> bool:
        try:
            return (
                bool(self.ctl.cfg.get("pro_autoping_enabled", True))
                and self.ctl.is_vpn
                and bool(self._vpn_servers)
            )
        except Exception:
            return False

    def _preping_work(self) -> None:
        """Пинг всех серверов подписки → выбрать лучший → включить VPN."""
        servers = list(self._vpn_servers)
        results: Dict[str, int] = {}
        try:
            from concurrent.futures import ThreadPoolExecutor

            def _ping_one(srv: Dict[str, str]) -> None:
                host = str(srv.get("server", ""))
                port = srv.get("server_port", 0)
                try:
                    ms = singbox_config.ping_server(host, int(port)) if host and port else -1
                except Exception:
                    ms = -1
                results[srv["tag"]] = ms
                self.after(0, lambda t=srv["tag"], m=ms: self.server_list.set_ping(t, m))

            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(_ping_one, servers))
        except Exception:
            log.exception("preping failed")

        def _continue() -> None:
            try:
                self.server_list.set_pinging(False)
            except Exception:
                pass
            alive = {t: m for t, m in results.items() if m >= 0}
            if alive:
                best = min(alive, key=alive.get)
                try:
                    self.server_list.set_selected(best)
                except Exception:
                    pass
                self._on_location_selected(best)
            threading.Thread(target=self._toggle_work, args=(True,),
                             daemon=True, name="toggle-work").start()

        self.after(0, _continue)

    def _after_toggle(self, value: bool) -> None:
        if value:
            _h = getattr(self, "_health", None)
            if _h is not None:
                _h.request_tick()

        self.toggle.set_busy(False)
        self._refresh_status_text()
        # уведомление о результате (ошибку уже показал _on_error)
        try:
            if value:
                if not self._error_text and self.ctl.is_on():
                    notify.send(self._enabled_notify_text())
            else:
                notify.send("Обход выключен")
        except Exception:
            log.exception("toggle notify failed")

    # ── update check ─────────────────────────────────────────────────
    def _schedule_update_check(self) -> None:
        """Запускаем фоновую проверку через секунду после старта окна,
        чтобы UI успел нарисоваться."""
        def _kick():
            try:
                check_async(self.ctl.cfg, self._on_update_available)
            except Exception:
                log.exception("update check kick failed")
        job = self.after(1500, _kick)
        self._after_jobs.append(job)

    def _on_update_available(self, info: dict) -> None:
        """Колбэк из фонового потока. Прыгаем в UI-thread."""
        self.after(0, lambda: self._show_update_dialog(info))

    def _show_update_dialog(self, info: dict) -> None:
        def _on_skip():
            snooze_for_three_days(self.ctl.cfg)
            try:
                save_config(self.ctl.cfg)
            except Exception:
                log.exception("failed to persist update_skip_until")
        try:
            notify.send((i18n.t('notify.update_available') + ' ' + str(info.get('tag', ''))).strip())
        except Exception:
            pass
        try:
            UpdateDialog(self, info, on_skip=_on_skip)
        except Exception:
            log.exception("failed to show update dialog")

    def _open_settings(self) -> None:
        was_on = self.ctl.is_on()
        prev_theme = str(self.ctl.cfg.get("theme", "dark"))
        prev_mode = str(self.ctl.cfg.get("game_mode", "normal"))
        prev_lang = str(self.ctl.cfg.get("language", "auto"))

        def _on_save(new_cfg: dict) -> None:
            self.ctl.cfg.update(new_cfg)
            self.ctl.save()
            # применяем автозапуск Windows к реестру
            try:
                autostart.apply(bool(new_cfg.get("autostart_with_windows", False)))
            except Exception:
                log.exception("autostart apply failed")
            # уведомления — ставим раньше трея, чтобы тосты шли через иконку
            notify.set_enabled(bool(new_cfg.get("notifications_enabled", True)))
            # tray: нужен для сворачивания, старта свёрнутым и тостов — поднять,
            # если включена хотя бы одна из функций, а иконки ещё нет
            want_tray = (
                bool(new_cfg.get("minimize_to_tray", True))
                or bool(new_cfg.get("start_minimized", False))
                or bool(new_cfg.get("notifications_enabled", True))
            )
            if want_tray and self._tray is None:
                self._init_tray()
            # тема меняется на месте — пересобираем основной UI
            new_theme = str(new_cfg.get("theme", "dark"))
            if new_theme != prev_theme:
                apply_theme(new_theme)
                self._rebuild_ui()
            elif (bool(new_cfg.get("hc_enabled", True)) != (getattr(self, "_health_row", None) is not None)
                  or str(new_cfg.get("language", "auto")) != prev_lang):
                # сменили мониторинг или язык — перерисовать UI на новом языке
                i18n.set_language(str(new_cfg.get("language", "auto")))
                self._rebuild_ui()
            # режим (обычный/гейминг) применяется при перезапуске zapret ниже
            new_mode = str(new_cfg.get("game_mode", "normal"))
            if was_on:
                self.ctl.restart_with_new_config()
            self._refresh_status_text()
            # уведомление о применённых настройках
            try:
                if was_on and not self._error_text and self.ctl.is_on():
                    if new_mode != prev_mode:
                        mode_ru = "гейминг" if new_mode == "gaming" else "обычный"
                        notify.send(i18n.t("notify.mode_changed", m=mode_ru))
                    else:
                        notify.send(i18n.t("notify.settings_applied"))
            except Exception:
                log.exception("settings notify failed")

        SettingsWindow(
            self, self.ctl.cfg, on_save=_on_save,
            controller=self.ctl, on_run_wizard=self._open_wizard,
        )

    def _open_dpitest(self) -> None:
        try:
            DpiTestDialog(self)
        except Exception:
            log.exception("dpi test dialog failed")

    def _open_tg_guide(self) -> None:
        try:
            TgVcGuideDialog(self, self.ctl.cfg)
        except Exception:
            log.exception("tg guide dialog failed")

    def _cycle_theme(self) -> None:
        themes = available_themes()
        cur = str(self.ctl.cfg.get("theme", "dark"))
        try:
            idx = themes.index(cur)
        except ValueError:
            idx = -1
        nxt = themes[(idx + 1) % len(themes)]
        self.ctl.cfg["theme"] = nxt
        self.ctl.save()
        apply_theme(nxt)
        self._rebuild_ui()

    def _rebuild_ui(self) -> None:
        """Пересобрать главное окно после смены темы.

        Сам объект ``THEME`` мутируется на месте, но виджеты Tk не пересчитывают
        свои цвета автоматически — поэтому уничтожаем содержимое окна и собираем
        заново. Все колбэки контроллера привязаны к ``self`` и переживают
        пересборку.
        """
        try:
            for w in self.winfo_children():
                w.destroy()
        except Exception:
            log.exception("rebuild: destroy children failed")
        self.configure(bg=THEME.bg)
        try:
            self.option_add("*Menu.background", THEME.card)
            self.option_add("*Menu.foreground", THEME.text_primary)
        except Exception:
            pass
        self._apply_mode_geometry()
        self._build()
        self._refresh_status_text()

    def _copy_link(self) -> None:
        cfg = self.ctl.cfg
        host = cfg.get("proxy_host", "127.0.0.1")
        port = cfg.get("proxy_port", 1443)
        secret = cfg.get("proxy_secret", "")
        link = f"tg://proxy?server={host}&port={port}&secret=dd{secret}"
        try:
            self.clipboard_clear()
            self.clipboard_append(link)
            self.update()
        except Exception:
            pass
        self._flash_hint("ссылка скопирована")

    def _flash_hint(self, text: str) -> None:
        prev = self.hint_lbl.cget("text")
        prev_color = self.hint_lbl.cget("fg")
        self.hint_lbl.configure(text=text, fg=THEME.accent_dim)
        self.after(1500, lambda: self.hint_lbl.configure(text=prev, fg=prev_color))

    # ── error surfacing ──────────────────────────────────────────────
    def _report_callback_exception(self, exc, val, tb) -> None:
        import traceback as _tb
        text = "".join(_tb.format_exception(exc, val, tb))
        try:
            log.error("uncaught Tk callback exception:\n%s", text)
        except Exception:
            pass
        try:
            self._show_error_dialog("Необработанная ошибка", text)
        except Exception:
            try:
                from tkinter import messagebox
                messagebox.showerror("EXDPI — ошибка", text[:1500])
            except Exception:
                pass

    def _show_error_dialog(self, title: str, body: str) -> None:
        """Копируемое окно с полным текстом ошибки (traceback не обрезается)."""
        win = tk.Toplevel(self)
        win.title(f"EXDPI — {title}")
        win.configure(bg=THEME.bg)
        try:
            win.transient(self)
        except Exception:
            pass
        win.geometry("660x440")
        win.minsize(420, 260)

        tk.Label(
            win, text=title, fg=THEME.danger, bg=THEME.bg,
            font=(THEME.font_ui, 12, "bold"), anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 2))
        tk.Label(
            win, text="Скопируй полный текст и пришли в чат — так я точно починю.",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 9), anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 8))

        frame = tk.Frame(win, bg=THEME.bg)
        frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        txt = tk.Text(
            frame, bg=THEME.card, fg=THEME.text_primary,
            insertbackground=THEME.accent, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=THEME.border,
            font=("Consolas", 9), wrap="word", padx=10, pady=8,
        )
        sb = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        txt.insert("1.0", body)
        txt.configure(state="disabled")

        row = tk.Frame(win, bg=THEME.bg)
        row.pack(fill="x", padx=16, pady=(0, 14))

        def _copy():
            try:
                self.clipboard_clear()
                self.clipboard_append(body)
                self.update()
            except Exception:
                pass

        copy_btn = tk.Label(
            row, text="  копировать  ", fg=THEME.bg, bg=THEME.accent,
            font=(THEME.font_ui, 10, "bold"), cursor="hand2", padx=14, pady=6,
        )
        copy_btn.pack(side="left")
        copy_btn.bind("<Button-1>", lambda _e: _copy())
        close_btn = tk.Label(
            row, text="закрыть", fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 10), cursor="hand2", padx=10, pady=6,
        )
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda _e: win.destroy())

    # ── иконка окна ────────────────────────────────────
    def _apply_window_icon(self) -> None:
        """Проставить иконку EXDPI на окно и в панель задач.

        Штатные Tk-вызовы iconbitmap/iconphoto на Windows часто не
        срабатывают (старый Tk не умеет PNG; ICO с PNG-фреймами
        грузится не везде) — тогда окно остаётся с дефолтным пером
        Tk. Поэтому после штатного пути дополнительно проставляем
        иконку напрямую через WinAPI (WM_SETICON), в обход Tk.
        """
        try:
            ico = paths.icon_ico()
            if ico.exists():
                self.iconbitmap(default=str(ico))
        except Exception:
            log.exception("iconbitmap failed")
        try:
            png = paths.icon_png()
            if png.exists():
                self._icon_photo = tk.PhotoImage(file=str(png))
                self.iconphoto(True, self._icon_photo)
        except Exception:
            log.exception("iconphoto failed")
        if sys.platform == "win32":
            try:
                self._apply_win32_icon()
            except Exception:
                log.exception("win32 window icon failed")

    def _apply_win32_icon(self) -> None:
        """Загрузить resources/icon.ico через WinAPI и повесить на HWND окна."""
        import ctypes
        ico = paths.icon_ico()
        if not ico.exists():
            return
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x00000010
        WM_SETICON = 0x0080
        ICON_SMALL, ICON_BIG = 0, 1
        GA_ROOT = 2
        SM_CXSMICON, SM_CYSMICON, SM_CXICON, SM_CYICON = 49, 50, 11, 12
        user32 = ctypes.windll.user32
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.LoadImageW.argtypes = [
            ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
            ctypes.c_int, ctypes.c_int, ctypes.c_uint,
        ]
        user32.SendMessageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p,
        ]
        user32.GetAncestor.restype = ctypes.c_void_p
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetSystemMetrics.restype = ctypes.c_int
        path = str(ico)
        cx_s = user32.GetSystemMetrics(SM_CXSMICON) or 16
        cy_s = user32.GetSystemMetrics(SM_CYSMICON) or 16
        cx_b = user32.GetSystemMetrics(SM_CXICON) or 32
        cy_b = user32.GetSystemMetrics(SM_CYICON) or 32
        hicon_small = user32.LoadImageW(None, path, IMAGE_ICON, cx_s, cy_s, LR_LOADFROMFILE)
        hicon_big = user32.LoadImageW(None, path, IMAGE_ICON, cx_b, cy_b, LR_LOADFROMFILE)
        # HWND верхнеуровневого окна: winfo_id() — дочернее, берём корень.
        self.update_idletasks()
        wid = self.winfo_id()
        hwnd = user32.GetAncestor(wid, GA_ROOT) or wid
        if hicon_small:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
        if hicon_big:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
        # держим хэндлы, чтобы иконки не выгрузились.
        self._hicon_small = hicon_small
        self._hicon_big = hicon_big

    # ── Win32 window visibility ─────────────────────────────────────
    def _win32_hwnd(self) -> Optional[int]:
        """HWND верхнеуровневого окна через WinAPI."""
        if sys.platform != "win32":
            return None
        try:
            import ctypes
            user32 = ctypes.windll.user32
            GA_ROOT = 2
            wid = self.winfo_id()
            hwnd = user32.GetAncestor(wid, GA_ROOT) or wid
            return hwnd
        except Exception:
            return None

    def _win32_hide(self) -> None:
        """Скрыть окно через WinAPI ShowWindow(SW_HIDE).

        В отличие от Tk withdraw(), не пересоздаёт запись в панели задач —
        Windows 10/11 оставляет одну иконку, и при показе она не дублируется.
        """
        hwnd = self._win32_hwnd()
        if hwnd:
            try:
                import ctypes
                SW_HIDE = 0
                ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
                return
            except Exception:
                pass
        self.withdraw()

    def _win32_show(self) -> None:
        """Показать окно через WinAPI ShowWindow(SW_SHOWNA).

        SW_SHOWNA (8) показывает окно без перевода фокуса — безопаснее для
        вызова из трея. В отличие от Tk deiconify(), не создаёт новую запись
        в панели задач Windows 10/11.
        """
        hwnd = self._win32_hwnd()
        if hwnd:
            try:
                import ctypes
                SW_SHOWNA = 8
                ctypes.windll.user32.ShowWindow(hwnd, SW_SHOWNA)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                self.lift()
                return
            except Exception:
                pass
        self.deiconify()
        self.lift()
        self.focus_force()

    # ── tray ────────────────────────────────────────────────────────
    def _init_tray(self) -> None:
        if self._tray is not None:
            return
        try:
            ico_png = paths.icon_png()
        except Exception:
            log.exception("icon path failed")
            return
        try:
            tray = TrayController(
                icon_path=ico_png,
                on_show=lambda: self.after(0, self._show_from_tray),
                on_toggle=lambda: self.after(0, self._tray_toggle),
                on_quit=lambda: self.after(0, self._quit_app),
                is_on_provider=lambda: self.ctl.is_on(),
                cfg_provider=lambda: self.ctl.cfg,
                on_strategy=(lambda s: self.after(0, self._tray_set_strategy, s))
                            if sys.platform == "win32" else None,
                on_mode=(lambda m: self.after(0, self._tray_set_mode, m))
                        if sys.platform == "win32" else None,
                on_dpitest=(lambda: self.after(0, self._tray_open_dpitest))
                           if sys.platform == "win32" else None,
                on_logs=lambda: self.after(0, self._tray_open_logs),
                on_settings=lambda: self.after(0, self._tray_open_settings),
            )
            if not tray.start():
                log.info("tray controller did not start")
                return
            self._tray = tray
            notify.register_tray(tray)
        except Exception:
            log.exception("tray init failed")

    def _tray_toggle(self) -> None:
        """Переключение из трея: инвертируем текущее состояние и синхронизируем
        большой переключатель в окне."""
        value = not self.ctl.is_on()
        try:
            self.toggle.set(value, animate=False)
        except Exception:
            pass
        self._on_toggle(value)

    def _tray_set_strategy(self, strategy: str) -> None:
        if str(self.ctl.cfg.get("zapret_strategy", "")) == strategy:
            return
        self.ctl.cfg["zapret_strategy"] = strategy
        self.ctl.save()
        if self.ctl.is_on():
            def _restart():
                try:
                    self.ctl.restart_with_new_config()
                except Exception:
                    log.exception("strategy restart failed")
                finally:
                    self.after(0, lambda: (
                        self._refresh_status_text(),
                        notify.send(i18n.t("notify.strategy_updated"))
                        if not self._error_text and self.ctl.is_on() else None,
                    ))
            threading.Thread(target=_restart, daemon=True, name="strategy-restart").start()
        else:
            self._refresh_status_text()

    def _tray_set_mode(self, mode: str) -> None:
        self._set_game_mode(mode)

    def _cycle_game_mode(self) -> None:
        """Переключить режим запрета normal ↔ gaming кликом по плашке."""
        cur = str(self.ctl.cfg.get("game_mode", "normal"))
        self._set_game_mode("normal" if cur == "gaming" else "gaming")

    def _set_game_mode(self, mode: str) -> None:
        """Сменить game_mode, сохранить и перезапустить обход (если включён),
        с уведомлением о результате. Используется плашкой, треем и мастером."""
        if mode not in ("normal", "gaming"):
            return
        if str(self.ctl.cfg.get("game_mode", "normal")) == mode:
            return
        self.ctl.cfg["game_mode"] = mode
        self.ctl.save()
        mode_ru = "гейминг" if mode == "gaming" else "обычный"
        if self.ctl.is_on():
            self._error_text = None
            def _restart():
                try:
                    self.ctl.restart_with_new_config()
                except Exception:
                    log.exception("mode restart failed")
                finally:
                    self.after(0, lambda: self._after_mode_change(mode_ru))
            threading.Thread(target=_restart, daemon=True, name="mode-restart").start()
        else:
            try:
                notify.send(f"Режим переключён: {mode_ru}")
            except Exception:
                pass
            self._refresh_status_text()

    def _after_mode_change(self, mode_ru: str) -> None:
        self._refresh_status_text()
        try:
            if not self._error_text and self.ctl.is_on():
                notify.send(i18n.t("notify.mode_changed", m=mode_ru))
        except Exception:
            log.exception("mode notify failed")

    def _tray_open_dpitest(self) -> None:
        self._show_from_tray()
        self._open_dpitest()

    def _tray_open_logs(self) -> None:
        try:
            logs.open_logs_folder()
        except Exception:
            log.exception("open logs folder failed")

    def _tray_open_settings(self) -> None:
        self._show_from_tray()
        self._open_settings()

    # ── мастер первого запуска ──────────────────────────────────────
    def _open_wizard(self) -> None:
        try:
            self._show_from_tray()
        except Exception:
            pass

        def _on_finish(data: dict) -> None:
            prev_theme = str(self.ctl.cfg.get("theme", "dark"))
            self.ctl.cfg.update(data)
            self.ctl.save()
            try:
                autostart.apply(bool(self.ctl.cfg.get("autostart_with_windows", False)))
            except Exception:
                log.exception("autostart apply failed")
            notify.set_enabled(bool(self.ctl.cfg.get("notifications_enabled", True)))
            want_tray = (
                bool(self.ctl.cfg.get("minimize_to_tray", True))
                or bool(self.ctl.cfg.get("start_minimized", False))
                or bool(self.ctl.cfg.get("notifications_enabled", True))
            )
            if want_tray and self._tray is None:
                self._init_tray()
            # тема могла меняться живьём в мастере — применяем и пересобираем всегда
            apply_theme(str(self.ctl.cfg.get("theme", "dark")))
            self._rebuild_ui()
            if self.ctl.is_on():
                self.ctl.restart_with_new_config()
            self._refresh_status_text()

        try:
            FirstRunWizard(self, self.ctl.cfg, controller=self.ctl, on_finish=_on_finish)
        except Exception:
            log.exception("wizard failed")

    def _show_from_tray(self) -> None:
        try:
            self._win32_show()
        except Exception:
            log.exception("show from tray failed")

    def _quit_app(self) -> None:
        """Действительно закрыть приложение (из меню трея или, если трея нет,
        по крестику окна)."""
        if self._quitting:
            return
        self._quitting = True
        notify.unregister_tray()
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:
                pass
            self._tray = None
        try:
            self.ctl.stop()
        except Exception:
            log.exception("controller stop failed")
        # Pro-сервисы
        for _svc in ("_watchdog", "_hotkeys", "_health"):
            _s = getattr(self, _svc, None)
            if _s is None or not hasattr(_s, "stop"):
                try:
                    _s.stop()
                except Exception:
                    pass
        for j in self._after_jobs:
            try:
                self.after_cancel(j)
            except Exception:
                pass
        try:
            self.destroy()
        except Exception:
            pass

    def _on_close(self) -> None:
        # если включено сворачивание в трей — не закрываем приложение
        if bool(self.ctl.cfg.get("minimize_to_tray", True)) and not self._quitting:
            # трей мог не подняться (например, pystray недоступен) — пробуем
            # поднять его лениво, чтобы окно не «потерялось» без иконки.
            if self._tray is None:
                self._init_tray()
            if self._tray is not None:
                try:
                    self._win32_hide()
                except Exception:
                    log.exception("withdraw failed")
                return
            # трея так и нет — сворачиваем в панель задач, окно не теряется
            try:
                self.iconify()
                return
            except Exception:
                log.exception("iconify fallback failed")
        # иначе — обычный полный выход
        self._quit_app()


