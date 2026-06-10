"""Главное окно: минималистичный экран с большим переключателем."""
from __future__ import annotations

import logging
import threading
import tkinter as tk
from typing import Optional

from . import __version__, autostart, easter, logs, notify, paths
from .config import save as save_config
from .controller import Controller
from .theme import THEME, apply_theme, available_themes
from .tray import TrayController
from .ui_dpitest import DpiTestDialog
from .ui_settings import SettingsWindow
from .ui_tg_guide import TgVcGuideDialog
from .ui_wizard import FirstRunWizard
from .updater import UpdateDialog, check_async, snooze_for_three_days
from .widgets import AnimatedToggle, IconButton, StatusDot

log = logging.getLogger("dpibypass.ui")


class App(tk.Tk):
    WIDTH = 400
    HEIGHT = 400
    MIN_WIDTH = 400
    MIN_HEIGHT = 400

    def __init__(self) -> None:
        super().__init__()

        self.ctl = Controller()
        self.ctl.bind(on_state=self._on_state, on_error=self._on_error)

        self._error_text: Optional[str] = None
        self._after_jobs: list[str] = []
        self._tray: Optional[TrayController] = None
        self._quitting = False

        self.title("EXDPI")
        self.configure(bg=THEME.bg)
        self.resizable(True, True)
        self.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self._center_on_screen()

        try:
            ico = paths.icon_ico()
            if ico.exists():
                self.iconbitmap(default=str(ico))
        except Exception:
            pass

        # Дополнительно ставим PNG как iconphoto — на HiDPI Windows иногда
        # берёт именно его, и иконка получается резче.
        try:
            png = paths.icon_png()
            if png.exists():
                self._icon_photo = tk.PhotoImage(file=str(png))
                self.iconphoto(True, self._icon_photo)
        except Exception:
            pass

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

        # tray-иконка: запускаем, если включено сворачивание в трей или
        # запуск свёрнутым — иначе она просто не нужна
        if self.ctl.cfg.get("minimize_to_tray", True) or self.ctl.cfg.get("start_minimized", False):
            self._init_tray()

        # уведомления Windows — по настройке
        notify.set_enabled(bool(self.ctl.cfg.get("notifications_enabled", True)))

        # запуск свёрнутым: окно прячется сразу, tray уже есть
        if self.ctl.cfg.get("start_minimized", False) and self._tray is not None:
            self.after(150, self.withdraw)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # мастер первого запуска — один раз
        if not bool(self.ctl.cfg.get("wizard_done", False)):
            self.after(400, self._open_wizard)

    # ── layout ───────────────────────────────────────────────────────
    def _center_on_screen(self) -> None:
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = (sw - self.WIDTH) // 2
        y = (sh - self.HEIGHT) // 2 - 40
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{max(0, x)}+{max(0, y)}")

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

        # ── center toggle area ───────────────────────────────────────
        center = tk.Frame(outer, bg=THEME.bg)
        center.pack(expand=True, fill="both")

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
            status_row, text="Отключено",
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
        )
        self.hint_lbl.pack(pady=(6, 0))

        # diagnostic link — открывает DPI-тест (TLS-handshake к набору хостов)
        self.diag_lbl = tk.Label(
            toggle_box, text="проверить обход",
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

        # подпись с текущим режимом zapret — обычный/гейминг
        self.mode_lbl = tk.Label(
            toggle_box, text="",
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 8, "bold"),
        )
        self.mode_lbl.pack(pady=(6, 0))

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

    # ── пасхалка ─────────────────────────────────────────────────────
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
        host = cfg.get("proxy_host", "127.0.0.1")
        port = cfg.get("proxy_port", 1443)
        self.info_lbl.configure(text=f"mtproto · {host}:{port}")

        mode = str(cfg.get("game_mode", "normal"))
        mode_text = "режим: гейминг" if mode == "gaming" else "режим: обычный"
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
            self.status_lbl.configure(text="Включено", fg=THEME.text_primary)
            self.dot.set_color(THEME.accent)
        else:
            self.status_lbl.configure(text="Отключено", fg=THEME.text_primary)
            self.dot.set_color(THEME.danger)

        if self._tray is not None:
            try:
                self._tray.update_state()
            except Exception:
                pass

    def _schedule_stats_refresh(self) -> None:
        try:
            stats = self.ctl.proxy.stats_snapshot() if self.ctl.proxy.is_running else None
        except Exception:
            stats = None

        if not self._error_text:
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
            self._error_text = msg[:60]
            self._refresh_status_text()
        self.after(0, _apply)
        try:
            notify.send(f"Ошибка: {msg[:120]}")
        except Exception:
            log.exception("error toast failed")

    # ── interactions ─────────────────────────────────────────────────
    def _on_toggle(self, value: bool) -> None:
        self._error_text = None
        self.toggle.set_busy(True)
        self.status_lbl.configure(text="…", fg=THEME.text_secondary)

        hidden = False
        try:
            hidden = self.state() == "withdrawn"
        except Exception:
            pass

        def _work():
            try:
                if value:
                    self.ctl.start()
                else:
                    self.ctl.stop()
                if hidden:
                    notify.send("Обход включён" if value else "Обход выключен")
            finally:
                self.after(0, self._after_toggle)

        threading.Thread(target=_work, daemon=True, name="toggle-work").start()

    def _after_toggle(self) -> None:
        self.toggle.set_busy(False)
        self._refresh_status_text()

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
            notify.send(('Доступно обновление ' + str(info.get('tag', ''))).strip())
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

        def _on_save(new_cfg: dict) -> None:
            self.ctl.cfg.update(new_cfg)
            self.ctl.save()
            # применяем автозапуск Windows к реестру
            try:
                autostart.apply(bool(new_cfg.get("autostart_with_windows", False)))
            except Exception:
                log.exception("autostart apply failed")
            # tray: если включено сворачивание/старт-в-трей, а иконки ещё нет — поднять
            want_tray = bool(new_cfg.get("minimize_to_tray", True)) or \
                bool(new_cfg.get("start_minimized", False))
            if want_tray and self._tray is None:
                self._init_tray()
            # тема меняется на месте — пересобираем основной UI
            new_theme = str(new_cfg.get("theme", "dark"))
            if new_theme != prev_theme:
                apply_theme(new_theme)
                self._rebuild_ui()
            # режим (обычный/гейминг) применяется только после перезапуска zapret
            new_mode = str(new_cfg.get("game_mode", "normal"))
            if was_on and new_mode != prev_mode:
                # restart ниже подхватит новое значение из cfg
                pass
            # уведомления
            notify.set_enabled(bool(new_cfg.get("notifications_enabled", True)))
            if was_on:
                self.ctl.restart_with_new_config()
            self._refresh_status_text()

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
                on_strategy=lambda s: self.after(0, self._tray_set_strategy, s),
                on_mode=lambda m: self.after(0, self._tray_set_mode, m),
                on_dpitest=lambda: self.after(0, self._tray_open_dpitest),
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
        self.ctl.cfg["zapret_strategy"] = strategy
        self.ctl.save()
        if self.ctl.is_on():
            threading.Thread(
                target=self.ctl.restart_with_new_config,
                daemon=True, name="tray-strategy-restart",
            ).start()
        self._refresh_status_text()

    def _tray_set_mode(self, mode: str) -> None:
        self.ctl.cfg["game_mode"] = mode
        self.ctl.save()
        if self.ctl.is_on():
            threading.Thread(
                target=self.ctl.restart_with_new_config,
                daemon=True, name="tray-mode-restart",
            ).start()
        self._refresh_status_text()

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
            want_tray = bool(self.ctl.cfg.get("minimize_to_tray", True)) or                 bool(self.ctl.cfg.get("start_minimized", False))
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
            self.deiconify()
            self.lift()
            self.focus_force()
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
        # если включено сворачивание в трей и tray работает — прячем окно
        if (
            self._tray is not None
            and bool(self.ctl.cfg.get("minimize_to_tray", True))
            and not self._quitting
        ):
            try:
                self.withdraw()
            except Exception:
                log.exception("withdraw failed")
            return
        # иначе — обычный полный выход
        self._quit_app()
