"""Локализация интерфейса (появилось в 3.0): русский и английский.

Язык берётся из конфига (``language``: "auto" | "ru" | "en"); "auto" — по
языку системы. ``t(key)`` возвращает строку на текущем языке; таблица
``STRINGS`` покрывает основные поверхности (трей, главное окно, статусные
тексты и уведомления, заголовки настроек). Виджеты читают t() при
построении — смена языка применяется при пересборке UI (после «сохранить»
в настройках или перезапуска).

Добавляя новый текст в UI, кладите строку в STRINGS и оборачивайте в t().
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

log = logging.getLogger("dpibypass.i18n")

_LANG = "ru"

STRINGS: Dict[str, Dict[str, str]] = {
    # ── трей ──────────────────────────────────────────────────────────
    "tray.open": {"ru": "Открыть EXDPI", "en": "Open EXDPI"},
    "tray.toggle_on": {"ru": "Выключить", "en": "Turn off"},
    "tray.toggle_off": {"ru": "Включить", "en": "Turn on"},
    "tray.toggle_default": {"ru": "Переключить", "en": "Toggle"},
    "tray.strategy": {"ru": "Стратегия", "en": "Strategy"},
    "tray.mode": {"ru": "Режим", "en": "Mode"},
    "tray.dpitest": {"ru": "Проверить обход", "en": "Test bypass"},
    "tray.logs": {"ru": "Папка с логами", "en": "Logs folder"},
    "tray.settings": {"ru": "Настройки", "en": "Settings"},
    "tray.quit": {"ru": "Выход", "en": "Quit"},
    "tray.auto": {"ru": "Авто", "en": "Auto"},
    "tray.auto_full": {"ru": "Авто (подбор лучшей)", "en": "Auto (best pick)"},
    "tray.mode_normal": {"ru": "Обычный", "en": "Normal"},
    "tray.mode_gaming": {"ru": "Гейминг", "en": "Gaming"},
    "tray.status_on": {"ru": "Обход включён", "en": "Bypass is on"},
    "tray.status_off": {"ru": "Обход выключен", "en": "Bypass is off"},

    # ── главное окно ─────────────────────────────────────────────────
    "main.off": {"ru": "Отключено", "en": "Off"},
    "main.on": {"ru": "Включено", "en": "On"},
    "main.off_vpn": {"ru": "VPN: отключён", "en": "VPN: off"},
    "main.monitoring": {"ru": "мониторинг:", "en": "monitoring:"},
    "main.best_server": {"ru": "подбираю лучший сервер…", "en": "picking the best server…"},
    "main.test_bypass": {"ru": "проверить обход", "en": "test bypass"},
    "main.mode_normal": {"ru": "обычный", "en": "normal"},
    "main.mode_gaming": {"ru": "гейминг", "en": "gaming"},
    "main.mode_change": {"ru": "режим: {m} · сменить", "en": "mode: {m} · change"},
    "main.status_on_mode": {"ru": "Обход включён · режим: {m}", "en": "Bypass is on · mode: {m}"},

    # ── настройки ─────────────────────────────────────────────────────
    "set.title": {"ru": "EXDPI · настройки", "en": "EXDPI · settings"},
    "set.tab_general": {"ru": "Общее", "en": "General"},
    "set.tab_advanced": {"ru": "Дополнительно", "en": "Advanced"},
    "set.save": {"ru": "  сохранить  ", "en": "  save  "},
    "set.cancel": {"ru": "отмена", "en": "cancel"},
    "set.settings": {"ru": "НАСТРОЙКИ", "en": "SETTINGS"},
    "set.lang_label": {"ru": "Язык интерфейса", "en": "Interface language"},

    # ── уведомления ───────────────────────────────────────────────────
    "notify.settings_applied": {
        "ru": "Настройки применены · обход перезапущен",
        "en": "Settings applied · bypass restarted"},
    "notify.mode_changed": {
        "ru": "Режим: {m} · обход перезапущен",
        "en": "Mode: {m} · bypass restarted"},
    "notify.strategy_updated": {
        "ru": "Стратегия обновлена · обход перезапущен",
        "en": "Strategy updated · bypass restarted"},
    "notify.health_switched": {
        "ru": "Сервисы недоступны на «{old}» — переключился на «{new}». Всё работает.",
        "en": "Services unreachable on '{old}' — switched to '{new}'. All good."},
    "notify.health_zapret_dead": {
        "ru": "zapret не запускается (код 1). Частая причина — запущена вторая "
              "копия EXDPI или другой zapret: закройте её и включите обход снова.",
        "en": "zapret won't start (code 1). Often another EXDPI copy or other "
              "zapret is running: close it and turn the bypass on again."},
    "notify.health_failed": {
        "ru": "Автопереключение не помогло — вернул стратегию «{old}». Попробуйте VPN-режим.",
        "en": "Auto-switch failed — restored '{old}'. Try the VPN mode."},
    "notify.update_available": {"ru": "Доступно обновление", "en": "Update available"},
}


def detect_lang() -> str:
    """Язык системы: 'ru' или 'en' (всё прочее → en)."""
    try:
        import ctypes
        windll = ctypes.windll  # Windows
        lid = windll.kernel32.GetUserDefaultUILanguage() & 0xFF
        return "ru" if lid == 0x19 else "en"
    except Exception:
        try:
            import locale
            return "ru" if locale.getdefaultlocale()[0] and \
                locale.getdefaultlocale()[0].startswith("ru") else "en"
        except Exception:
            return "en"


def set_language(lang: str) -> None:
    """Установить текущий язык ('auto' | 'ru' | 'en')."""
    global _LANG
    if lang == "ru" or lang == "en":
        _LANG = lang
    else:
        _LANG = detect_lang()
    log.debug("i18n language: %s", _LANG)
    ensure_hook()


_HOOK_INSTALLED = False


def _tr_text(s: str) -> str:
    """Статический RU-текст → EN по таблице (i18n_en.EN)."""
    try:
        from .i18n_en import EN
    except Exception:
        return s
    return EN.get(s, s)


def ensure_hook() -> None:
    """Полный перевод интерфейса на уровне Tk.

    t() покрывает только места, где он расставлен руками. Остальной
    интерфейс (настройки, мастер, диалоги) создаёт надписи напрямую,
    поэтому перехватываем Misc._options — единую точку, через которую
    проходят и создание виджета, и configure(). Для text= подставляем
    английский вариант из таблицы, если язык EN. Русский интерфейс
    не меняется вообще (хук пропускает всё при _LANG != "en").
    """
    global _HOOK_INSTALLED
    if _HOOK_INSTALLED:
        return
    _HOOK_INSTALLED = True
    try:
        import tkinter as tk
    except Exception:
        return
    if getattr(tk.Misc, "_exdpi_i18n_patched", False):
        return

    orig_options = tk.Misc._options

    def _options(self, cnf=None, kw=None):
        try:
            if _LANG == "en" and (cnf or kw):
                cnf = dict(cnf) if cnf else None
                kw = dict(kw) if kw else None
                for d in (cnf, kw):
                    if d and "text" in d and isinstance(d["text"], str):
                        d["text"] = _tr_text(d["text"])
        except Exception:
            pass
        return orig_options(self, cnf, kw)

    tk.Misc._options = _options
    tk.Misc._exdpi_i18n_patched = True


def current_lang() -> str:
    return _LANG


def t(key: str, **kwargs) -> str:
    """Строка по ключу на текущем языке; {placeholders} подставляются."""
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(_LANG) or entry.get("ru") or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            log.warning("i18n format failed for %s", key)
    return text
