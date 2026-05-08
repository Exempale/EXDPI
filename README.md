# EXDPI — zapret + tg-ws-proxy в одном окне

Автор сборки: **Exempale**. Логика обхода и прокси целиком взята из оригинальных
репозиториев основных авторов — этот проект только объединяет их в один GUI.

* **[zapret-discord-youtube]** — обход DPI через WinDivert (`winws.exe`) для Discord, YouTube и пр.
* **[tg-ws-proxy]** — локальный MTProto-прокси для Telegram, который ходит к DC через WebSocket.

Один большой переключатель, иконка шестерёнки, тёмная тема. Без логов в окне, без лишних кнопок.

![preview](resources/icon.png)

---

## Запуск (готовый .exe)

1. Скачайте `EXDPI.exe`.
2. Запустите. Программа сама запросит права администратора (UAC) — это нужно
   для драйвера WinDivert, который ловит пакеты на сетевом уровне.
3. Щёлкните по большому переключателю — оба сервиса (zapret + локальный
   MTProto-прокси) поднимутся одновременно.
4. Кнопка-иконка справа сверху → настройки (стратегия zapret, порт, секрет).
5. Кликом по 📋 рядом с `mtproto · 127.0.0.1:1443` копируется `tg://proxy?…`
   ссылка для импорта в Telegram Desktop.

Чтобы программа использовала прокси в Telegram Desktop:
**Настройки → Продвинутые → Тип соединения → Использовать пользовательский прокси →**
вставить скопированную `tg://proxy?...` ссылку.

### Системные требования

* Windows 10 (1809+) или Windows 11, x64.
* Права администратора (UAC) — для загрузки драйвера WinDivert.
* Telegram Desktop — для использования встроенного MTProto-прокси.

---

## Структура

```
EXDPI/
├── main.py                 # Точка входа + UAC-эскалация
├── manifest.xml            # requireAdministrator
├── version_info.txt        # Метаданные exe
├── build.spec              # PyInstaller spec
├── app/
│   ├── theme.py            # Цвета, шрифты
│   ├── widgets.py          # AnimatedToggle, IconButton, StatusDot
│   ├── ui_app.py           # Главное окно
│   ├── ui_settings.py      # Окно настроек
│   ├── controller.py       # Стейт + объединение zapret и proxy
│   ├── zapret_runner.py    # Парсер .bat и запуск winws.exe
│   ├── proxy_runner.py     # Запуск tg-ws-proxy в фоновом потоке
│   ├── config.py           # JSON-конфиг в %APPDATA%\EXDPI
│   └── paths.py            # Резолв ресурсов (dev/PyInstaller onefile)
├── proxy/                  # Исходники tg-ws-proxy (без изменений)
└── resources/
    ├── icon.ico
    ├── icon.png
    └── zapret/             # winws.exe + WinDivert + general*.bat + lists/
```

Конфиг хранится в `%APPDATA%\EXDPI\config.json`. Удалите файл — параметры
сбросятся к дефолтам.

---

## Сборка из исходников

Понадобится Windows + Python 3.11+.

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate

pip install -U pip
pip install pyinstaller customtkinter Pillow pyperclip cryptography psutil pystray

pyinstaller --noconfirm --clean build.spec
```

Результат — `dist\EXDPI.exe` (single-file, ≈17 МБ).

> При желании добавьте `upx=True` в `build.spec` и UPX в `PATH`, чтобы ужать
> бинарник примерно вдвое.

---

## Лицензии и происхождение

* Сборка / GUI — **Exempale** (`nevafav`).
* zapret-discord-youtube — Flowseal / bol-van (см. оригинальный репозиторий).
  Бинарь `winws.exe`, драйвер WinDivert и `general*.bat` стратегии взяты
  из оригинального релиза без изменений.
* tg-ws-proxy — оригинальный код в `proxy/`, не модифицирован.
* Иконка — предоставлена пользователем.

[zapret-discord-youtube]: https://github.com/Flowseal/zapret-discord-youtube
[tg-ws-proxy]: https://github.com/tg-ws-proxy/tg-ws-proxy
