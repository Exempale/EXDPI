# -*- coding: utf-8 -*-
"""Английские переводы статических надписей интерфейса.

Таблица RU -> EN для хука из app/i18n.ensure_hook(): на языке EN любой
виджет, создаваемый с русским text=, получает английский вариант. Ключи —
ТОЧНЫЕ строковые литералы из кода (после конкатенации). Динамические
f-строки и докстринги не переводятся (не попадают в виджеты либо
остаются как есть).
"""

EN = {
    # ── шапка/статусы, дублируем на всякий случай ────────────────────
    "ОБХОД": "BYPASS",
    "Отключено": "Off",
    "Включено": "On",
    "VPN: отключён": "VPN: off",
    "VPN: подключён": "VPN: connected",
    "проверить обход": "test bypass",
    "подключить прокси в Telegram": "connect proxy in Telegram",
    "режим: обычный · сменить": "mode: normal · change",
    "режим: гейминг · сменить": "mode: gaming · change",
    "обычный": "normal",
    "гейминг": "gaming",
    "Обход выключен": "Bypass is off",
    "автор · Exempale": "author · Exempale",
    "закрыть": "close",
    "Настройки": "Settings",
    "Ошибка": "Error",
    "ошибка": "error",

    # ── серверы (widgets) ─────────────────────────────────────────────
    "серверы: —": "servers: none",
    "серверы: найдено ": "servers: found ",
    "ссылка не задана": "link not set",
    "  обновить  ": "  refresh  ",
    "  пинг  ": "  ping  ",
    "  сортировка  ": "  sort  ",
    "  обновляю…  ": "  refreshing…  ",
    "  замер…  ": "  measuring…  ",
    " мс": " ms",
    "нет серверов": "no servers",
    "нет соединений": "no connections",
    "подписка: найдено ": "subscription: found ",
    "подписка: ": "subscription: ",
    "проверка подписки…": "checking subscription…",
    "всего: ": "total: ",
    " активн. · всего ": " active · total ",
    " серверов": " servers",
    "выбран самый быстрый сервер": "picked the fastest server",
    "ссылка скопирована": "link copied",
    "Скопировать MTProto-ссылку": "Copy MTProto link",
    "импорт .conf (WireGuard)": "import .conf (WireGuard)",
    "Режим переключён: ": "Mode changed: ",
    "Ошибка: ": "Error: ",
    " · обфускация AmneziaWG движком не поддерживается — подключение как обычный WireGuard":
        " · AmneziaWG obfuscation is not supported by the core — connecting as plain WireGuard",
    "Импортирован ": "Imported ",

    # ── настройки: заголовки и вкладки ────────────────────────────────
    "EXDPI · настройки": "EXDPI · settings",
    "НАСТРОЙКИ": "SETTINGS",
    "Настройки EXDPI": "EXDPI settings",
    "Общее": "General",
    "Дополнительно": "Advanced",
    "  сохранить  ": "  save  ",
    "отмена": "cancel",
    "автор · Exempale": "author · Exempale",
    "сборка поверх zapret-discord-youtube и tg-ws-proxy":
        "built on top of zapret-discord-youtube and tg-ws-proxy",
    "ориг. авторы: Flowseal / bol-van · tg-ws-proxy":
        "original authors: Flowseal / bol-van · tg-ws-proxy",

    # ── секционные заголовки (проходят через .upper()) ───────────────
    'СТРАТЕГИЯ ОБХОДА (ZAPRET)': 'BYPASS STRATEGY (ZAPRET)',
    'РЕЖИМ ЗАПРЕТА': 'BLOCK MODE',
    'ПОРТ ПРОКСИ': 'PROXY PORT',
    'ГОТОВЫЕ КОНФИГ-ЛИСТЫ': 'READY-MADE DOMAIN PRESETS',
    'СВОИ ДОМЕНЫ ДЛЯ ОБХОДА': 'CUSTOM DOMAINS',
    'DNS-ПРОВАЙДЕР (В ТУННЕЛЕ)': 'DNS PROVIDER (INSIDE TUNNEL)',
    'ДНС-ПРОВАЙДЕР': 'DNS PROVIDER',
    'ПРОТОКОЛ ЗАЩИЩЁННОГО DNS': 'SECURE DNS PROTOCOL',
    'НАЗНАЧАТЬ СИСТЕМНЫМ DNS': 'SET AS SYSTEM DNS',
    'СЕТЕВОЙ СТЕК TUN': 'TUN NETWORK STACK',
    'MTU ТУННЕЛЯ (576–9000)': 'TUNNEL MTU (576–9000)',
    'IPV6 В ТУННЕЛЕ': 'IPV6 INSIDE TUNNEL',
    'БЛОКИРОВАТЬ QUIC': 'BLOCK QUIC',
    'РОССИЯ — НАПРЯМУЮ': 'RUSSIA — DIRECT',
    'АВТО-ВЫБОР БЫСТРЕЙШЕГО': 'AUTO-PICK THE FASTEST',
    'ПРОЦЕССЫ (.EXE)': 'PROCESSES (.EXE)',
    'НАПРАВЛЕНИЕ ВЫБРАННЫХ ПРОЦЕССОВ': 'DIRECTION FOR SELECTED PROCESSES',

    # ── настройки: вкладка DPI ────────────────────────────────────────
    "Стратегия обхода (zapret)": "Bypass strategy (zapret)",
    "«Авто» использует результат авто-подбора": "'Auto' uses the auto-pick result",
    "последний авто-подбор: ": "last auto-pick: ",
    "подобрать автоматически": "pick automatically",
    "Режим запрета": "Block mode",
    "Обычный — фильтр только по стандартным TLS/HTTP/QUIC портам. Гейминг — GameFilter=1024-65535 для TCP+UDP: голос Discord, игровые лобби, P2P.":
        "Normal — standard TLS/HTTP/QUIC ports only. Gaming — GameFilter=1024-65535 for TCP+UDP: Discord voice, game lobbies, P2P.",
    "Порт прокси": "Proxy port",
    "Хост (только локально)": "Host (local only)",
    "Секрет (32 hex)": "Secret (32 hex)",
    "сгенерировать новый": "generate new",
    "Свои домены для обхода": "Custom domains",
    "Hostname по одному на строку или через ; . Попадают в list-general-user.txt zapret. Изменения применяются при следующем включении EXDPI.":
        "One hostname per line or separated by ; . Goes into zapret's list-general-user.txt. Applied on next EXDPI toggle.",
    "Готовые конфиг-листы": "Ready-made domain presets",
    "Подборки доменов одним кликом: ИИ, игры, соцсети, РФ-блоки. «Свой набор» — пользовательский список (сохраняется отдельно).":
        "One-click domain packs: AI, games, socials, RU blocks. 'Custom' is your own list (stored separately).",
    "загрузить .txt": "load .txt",
    "очистить": "clear",
    "  запустить service.bat  ": "  run service.bat  ",
    "Откроет консольное меню zapret (запросит права администратора).":
        "Opens the zapret console menu (asks for administrator).",
    "Откроет консольное меню zapret (только на Windows).":
        "Opens the zapret console menu (Windows only).",
    "  копировать  ": "  copy  ",
    "добавить .exe…": "add .exe…",
    "удалить": "remove",
    "ПРОЦЕССЫ (.exe)": "PROCESSES (.exe)",
    "Раздельное туннелирование (по процессам)": "Split tunneling (per process)",
    "Выбранные .exe идут в туннель, остальной трафик — мимо (или наоборот). Работает в VPN-режиме.":
        "Selected .exe go through the tunnel, the rest goes direct (or vice versa). Works in VPN mode.",
    "Направление выбранных процессов": "Direction for selected processes",
    "в туннель (остальное напрямую)": "tunnel them (rest goes direct)",
    "напрямую (остальное в туннель)": "direct them (rest goes to tunnel)",
    "Программы": "Programs",
    "Все файлы": "All files",
    "Выберите .exe для туннелирования": "Choose an .exe to tunnel",
    "Текстовый файл": "Text file",
    "Выбрать .txt со списком доменов": "Choose a .txt with the domain list",

    # ── настройки: вкладка VPN ────────────────────────────────────────
    "Настройки режима VPN (sing-box). Применяются при следующем подключении. Если после включения VPN пропадает интернет — поставьте стек «Mixed», MTU 1500 и выключите kill-switch.":
        "VPN mode settings (sing-box). Applied on next connect. If the internet dies after enabling VPN — set stack to 'Mixed', MTU 1500 and turn kill-switch off.",
    "DNS-провайдер (в туннеле)": "DNS provider (inside tunnel)",
    "DNS-провайдер": "DNS provider",
    "Протокол защищённого DNS": "Secure DNS protocol",
    "DoH — DNS-over-HTTPS (порт 443)": "DoH — DNS-over-HTTPS (port 443)",
    "DoT — DNS-over-TLS (порт 853)": "DoT — DNS-over-TLS (port 853)",
    "Назначать системным DNS": "Set as system DNS",
    "При включении прописывает 127.0.0.1 на активные адаптеры (старые DNS сохраняются и восстанавливаются при выключении).":
        "When enabled, sets 127.0.0.1 on active adapters (previous DNS is saved and restored on disable).",
    "Сетевой стек TUN": "TUN network stack",
    "Mixed (рекомендуется)": "Mixed (recommended)",
    "MTU туннеля (576–9000)": "Tunnel MTU (576–9000)",
    "IPv6 в туннеле": "IPv6 inside tunnel",
    "Включить IPv6 внутри VPN. Оставьте выключенным, если сервер/провайдер не поддерживает IPv6.":
        "Enable IPv6 inside the VPN. Leave off if your server/provider lacks IPv6.",
    "Блокировать QUIC": "Block QUIC",
    "Режет UDP/443 — браузер откатывается на TCP. Часто чинит «сайт открылся, а видео/стрим не идёт» под VPN.":
        "Cuts UDP/443 so browsers fall back to TCP. Often fixes 'site opens but video won't play' under VPN.",
    "Россия — напрямую": "Russia — direct",
    "Домены .ru/.su/.рф идут мимо VPN (быстрее, меньше блокировок). Остальное — через туннель.":
        "Domains .ru/.su/.рф bypass the VPN (faster, fewer blocks). The rest goes through the tunnel.",
    "Авто-выбор быстрейшего": "Auto-pick the fastest",
    "После замера пинга автоматически подключаться к самому быстрому серверу из подписки.":
        "After the ping test, connect to the fastest server from the subscription automatically.",
    "Kill-switch (strict route)": "Kill-switch (strict route)",
    "Строгая маршрутизация: если туннель упал — трафик НЕ пойдёт мимо VPN. Осторожно: на Windows может рубить весь трафик.":
        "Strict routing: if the tunnel dies, traffic will NOT leak around the VPN. Careful: can cut all traffic.",
    "Строгая маршрутизация: если туннель упал — трафик НЕ пойдёт мимо VPN. Осторожно: strict_route может рубить весь трафик.":
        "Strict routing: if the tunnel dies, traffic will NOT leak around the VPN. Careful: strict_route can cut all traffic.",

    # ── настройки: вкладка Общее ──────────────────────────────────────
    "Запускать с Windows": "Start with Windows",
    "Запускать при входе в систему": "Start at login",
    "Автозапуск при входе в систему через Планировщик заданий — сразу с правами администратора, без запроса UAC.":
        "Runs at login via Task Scheduler — already elevated, no UAC prompt.",
    "Автозапуск при входе в систему через LaunchAgent. Для DPI-обхода запускайте EXDPI через sudo.":
        "Runs at login via LaunchAgent. For DPI bypass, run EXDPI with sudo.",
    "Автозапуск при входе в систему через XDG autostart. Для DPI-обхода запускайте EXDPI через sudo.":
        "Runs at login via XDG autostart. For DPI bypass, run EXDPI with sudo.",
    "Включать обход при запуске": "Enable bypass on start",
    "При старте EXDPI (в том числе автозапуске с Windows) обход включается сам — система загрузилась, обход уже работает.":
        "When EXDPI starts (including system autostart), the bypass turns on by itself — the system boots with the bypass already working.",
    "При старте EXDPI (в том числе при автозапуске) обход включается сам — система загрузилась, обход уже работает.":
        "When EXDPI starts (including system autostart), the bypass turns on by itself — the system boots with the bypass already working.",
    "Сворачивать в трей": "Minimize to tray",
    "По крестику окно прячется в трей вместо выхода.":
        "Closing the window hides it to the tray instead of quitting.",
    "Запускать свёрнутым": "Start minimized",
    "При старте программа сразу уходит в трей.": "The app starts hidden in the tray right away.",
    "Уведомления Windows": "Windows notifications",
    "Уведомления системы": "System notifications",
    "Тосты о включении/выключении обхода, ошибках и обновлениях.":
        "Toasts about bypass on/off, errors and updates.",
    "Тема интерфейса": "Interface theme",
    "Цветовая схема приложения. Применяется сразу.": "App color scheme. Applied instantly.",
    "Русский": "Russian",
    "Auto · как в системе": "Auto · follow system",
    "Для разработчиков": "Developer mode",
    "ДЛЯ РАЗРАБОТЧИКОВ": "DEVELOPER",
    "Сервисные инструменты: логи, импорт/экспорт настроек, мастер первого запуска и запуск service.bat.":
        "Service tools: logs, settings import/export, first-run wizard and service.bat.",
    "открыть папку с логами": "open logs folder",
    "импортировать настройки…": "import settings…",
    "экспортировать настройки…": "export settings…",
    "мастер первого запуска": "first-run wizard",
    "дефолты": "defaults",
    "Импорт настроек EXDPI": "Import EXDPI settings",
    "Экспорт настроек EXDPI": "Export EXDPI settings",
    "Настройки экспортированы.": "Settings exported.",
    "Импорт не удался: ": "Import failed: ",
    "Загружено настроек: ": "Loaded settings: ",
    "Не удалось открыть настройки": "Could not open settings",
    "Не удалось открыть папку с логами.": "Could not open the logs folder.",
    "Не удалось сохранить файл.": "Could not save the file.",
    "Не удалось прочитать файл:\n": "Could not read the file:\n",
    "Исправьте подсвеченные поля перед экспортом.": "Fix the highlighted fields before export.",
    "Пресет пуст или файл со списком доменов не найден.": "Preset is empty or the domain file is missing.",
    "\nНажмите «сохранить», чтобы применить.": "\nPress 'save' to apply.",

    # ── настройки: вкладка Дополнительно ──────────────────────────────
    "Автовыбор лучшего пинга": "Best-ping auto-select",
    "Перед включением VPN EXDPI замерит задержку до всех локаций и выберет самую быструю.":
        "Before enabling VPN, EXDPI measures latency to every location and picks the fastest.",
    "Самовосстановление при сбоях": "Self-healing",
    "Watchdog следит за ядрами (winws/sing-box) и поднимает их обратно, если упали.":
        "The watchdog keeps the engines (winws/sing-box) alive and restarts them if they die.",
    "Облачные стратегии": "Cloud strategies",
    "Автообновление стратегий zapret с сервера без установки новой версии EXDPI.":
        "Zapret strategies update from the server without installing a new EXDPI build.",
    "Глобальные горячие клавиши": "Global hotkeys",
    "Переключатель ON/OFF из любого приложения (по комбинациям ниже).":
        "Turn the bypass on/off from any app (with the combos below).",
    "Комбинация для ON/OFF": "Hotkey for ON/OFF",
    "Комбинация для показать/скрыть окно": "Hotkey to show/hide the window",
    "Мониторинг сервисов": "Service monitoring",
    "EXDPI проверяет доступность YouTube / Discord / ChatGPT и показывает индикаторы в главном окне.":
        "EXDPI checks YouTube / Discord / ChatGPT reachability and shows indicators in the main window.",
    "Автопереключение стратегии": "Auto strategy switch",
    "Если сервис лёг на текущей стратегии, EXDPI сам переберёт остальные и включит рабочую (DPI-режим).":
        "If a service breaks on the current strategy, EXDPI tries the others and enables a working one (DPI mode).",
    "Как часто проверять сервисы": "How often to check services",
    "2 минуты": "2 minutes", "5 минут": "5 minutes",
    "10 минут": "10 minutes", "15 минут": "15 minutes",

    # ── мастер первого запуска ────────────────────────────────────────
    "EXDPI · первый запуск": "EXDPI · first run",
    "Добро пожаловать в EXDPI": "Welcome to EXDPI",
    "Обход DPI-блокировок, Telegram-прокси и защищённый DNS.\nСейчас всё настроим за минуту.":
        "DPI bypass, Telegram proxy and secure DNS.\nLet's set everything up in a minute.",
    "Что вам нужно?": "What do you need?",
    "Можно переключить в любой момент прямо в главном окне.":
        "You can switch anytime right in the main window.",
    "Обход DPI": "DPI bypass",
    "Разблокировка сайтов и сервисов через обход блокировок провайдера (zapret/WinDivert). Не шифрует весь трафик.":
        "Unblocks sites and services by bypassing provider blocking (zapret/WinDivert). Does not encrypt all traffic.",
    "Разблокировка сайтов и сервисов через обход блокировок провайдера (zapret/utunws). Не шифрует весь трафик.":
        "Unblocks sites and services by bypassing provider blocking (zapret/utunws). Does not encrypt all traffic.",
    "Разблокировка сайтов и сервисов через обход блокировок провайдера (zapret/nfqws). Не шифрует весь трафик.":
        "Unblocks sites and services by bypassing provider blocking (zapret/nfqws). Does not encrypt all traffic.",
    "VPN": "VPN",
    "Полноценный VPN-туннель через sing-box: по ссылке-подписке или прямому VLESS/SS/VMess/Trojan/Hysteria2/TUIC.":
        "Full VPN tunnel via sing-box: from a subscription link or direct VLESS/SS/VMess/Trojan/Hysteria2/TUIC.",
    "Выберите тему": "Pick a theme",
    "Мягкий тёмный интерфейс — глазам приятно ночью.": "Soft dark interface — easy on the eyes at night.",
    "Светлый и контрастный — для яркого дня.": "Light and contrasty — for a bright day.",
    "Применяется сразу. Потом можно переключить в один клик из главного окна.":
        "Applied instantly. You can switch later in one click from the main window.",
    "Что разблокируем?": "What should we unblock?",
    "Готовый набор доменов для обхода. Свои домены можно добавить позже в настройках.":
        "A ready-made domain pack. You can add your own domains later in settings.",
    "Пустой список — добавите свои домены в настройках.": "Empty list — add your own domains in settings.",
    "Режим обхода": "Bypass mode",
    "Фильтруются стандартные TLS/HTTP/QUIC порты. Подходит большинству.":
        "Only standard TLS/HTTP/QUIC ports are filtered. Good for most people.",
    "GameFilter 1024-65535 для TCP+UDP: голос Discord, игровые лобби, P2P.":
        "GameFilter 1024-65535 for TCP+UDP: Discord voice, game lobbies, P2P.",
    "Стратегия zapret": "Zapret strategy",
    "Стандартная (ALT10)": "Standard (ALT10)",
    "Проверенная стратегия по умолчанию. Авто-подбор можно запустить позже из настроек.":
        "The proven default strategy. Auto-pick can be run later from settings.",
    "Авто-подбор  ·  рекомендуется": "Auto-pick  ·  recommended",
    "«Авто» прогонит все стратегии и выберет ту, что реально пробивает блокировки у вашего провайдера (~1-2 минуты).":
        "'Auto' runs every strategy and picks the one that actually breaks through your provider's blocking (~1-2 minutes).",
    "Запустим каждую стратегию и измерим, сколько заблокированных хостов она открывает. Начнётся по кнопке «далее».":
        "We'll run each strategy and count how many blocked hosts it opens. Starts on 'next'.",
    "Тестирую ": "Testing ",
    " хостов, ": " hosts, ",
    "Готовлю прогон…": "Preparing the run…",
    "  подбираю…  ": "  picking…  ",
    "Авто-подбор не дал результата — будет стандартная стратегия.":
        "Auto-pick found nothing — the standard strategy will be used.",
    "Последние штрихи": "Finishing touches",
    "Всё это можно поменять в настройках в любой момент.": "All of this can be changed anytime in settings.",
    "Сворачивать в трей": "Minimize to tray",
    "По крестику окно прячется в трей, обход продолжает работать.":
        "Closing hides the window to the tray; the bypass keeps running.",
    "Защищённый DNS (DoH)": "Secure DNS (DoH)",
    "Локальный DNS-резолвер: запросы шифруются до Cloudflare, провайдер не видит и не подменяет их.":
        "Local DNS resolver: queries are encrypted to Cloudflare; your provider can't see or spoof them.",
    "Всё готово!": "All done!",
    "Нажмите «готово» и включайте большой переключатель.": "Press 'done' and flip the big toggle.",
    "  начать  →  ": "  start  →  ",
    "  далее  →  ": "  next  →  ",
    "←  назад": "←  back",
    "  готово  ✓  ": "  done  ✓  ",
    "пропустить": "skip",
    "Выбрана: ": "Selected: ",
    "Авто (": "Auto (",
    "Авто": "Auto",
    "Приложение: ": "App: ",
    "   ·   Домены: ": "   ·   Domains: ",
    "   ·   Стратегия: ": "   ·   Strategy: ",
    "   ·   Тема: ": "   ·   Theme: ",
    "\nРежим: ": "\nMode: ",
    "шаг 1 · режим работы": "step 1 · app mode",
    "шаг 2 · оформление": "step 2 · theme",
    "шаг 3 · домены": "step 3 · domains",
    "шаг 4 · режим": "step 4 · mode",
    "шаг 5 · стратегия": "step 5 · strategy",
    "шаг 6 · опции": "step 6 · options",
    "Обход DPI-блокировок, Telegram-прокси и защищённый DNS.": "DPI bypass, Telegram proxy and secure DNS.",
    "EXDPI стартует вместе с системой (HKCU\\…\\Run).": "EXDPI starts with the system (Task Scheduler, elevated).",
    "EXDPI стартует вместе с системой (Планировщик заданий, сразу с правами администратора).":
        "EXDPI starts with the system (Task Scheduler, already elevated).",
    "EXDPI стартует вместе с системой (LaunchAgent). Для DPI-обхода запускайте через sudo.":
        "EXDPI starts with the system (LaunchAgent). For DPI bypass, run with sudo.",
    "EXDPI стартует вместе с системой (XDG autostart). Для DPI-обхода запускайте через sudo.":
        "EXDPI starts with the system (XDG autostart). For DPI bypass, run with sudo.",
    "Тосты о включении/выключении обхода и ошибках.": "Toasts about bypass on/off and errors.",

    # ── telegram guide ────────────────────────────────────────────────
    "EXDPI · Telegram прокси": "EXDPI · Telegram proxy",
    "Telegram прокси / VC": "Telegram proxy / VC",
    "ИНСТРУКЦИЯ": "GUIDE",
    "ПАРАМЕТРЫ ВАШЕГО ПРОКСИ": "YOUR PROXY DETAILS",
    "Сервер:": "Server:",
    "Порт:": "Port:",
    "Секрет:": "Secret:",
    "Ссылка:": "Link:",
    "Тип:": "Type:",
    "MTPROTO (подходит и для VC)": "MTPROTO (works for VC too)",
    "  скопировать tg://proxy ссылку  ": "  copy the tg://proxy link  ",
    "Скопируйте ссылку кнопкой ниже и вставьте в Telegram — поля заполнятся сами.":
        "Copy the link below and paste it into Telegram — the fields fill in themselves.",
    "1. Откройте настройки Telegram Desktop": "1. Open Telegram Desktop settings",
    "«Настройки» → «Продвинутые настройки» → «Тип соединения».":
        "'Settings' → 'Advanced' → 'Connection type'.",
    "2. Добавьте MTPROTO-прокси": "2. Add an MTPROTO proxy",
    "«Использовать пользовательский прокси» → «Добавить прокси» → тип «MTPROTO».":
        "'Use custom proxy' → 'Add proxy' → type 'MTPROTO'.",
    "3. Введите параметры из блока выше": "3. Enter the details from the block above",
    "Сервер: 127.0.0.1. Порт и секрет — как указано выше.": "Server: 127.0.0.1. Port and secret — as above.",
    "4. Быстрее: вставьте готовую tg://-ссылку": "4. Faster: paste the ready tg:// link",
    "5. Включите EXDPI": "5. Turn EXDPI on",
    "Нажмите большой переключатель ON. В Telegram появится значок активного прокси.":
        "Flip the big toggle ON. Telegram will show an active-proxy icon.",
    "Голосовые чаты и звонки": "Voice chats and calls",
    "Голос идёт через тот же MTPROTO-прокси — отдельной настройки не требуется. Если слышимость хромает, в настройках EXDPI попробуйте другую стратегию zapret (general ALT10 / FAKE TLS AUTO / SIMPLE FAKE) или включите режим «гейминг».":
        "Voice goes through the same MTPROTO proxy — no extra setup. If audio is choppy, try another zapret strategy in EXDPI settings (general ALT10 / FAKE TLS AUTO / SIMPLE FAKE) or switch to 'gaming' mode.",
    "Закрыть": "Close",

    # ── dpi test ──────────────────────────────────────────────────────
    "EXDPI · диагностика": "EXDPI · diagnostics",
    "DPI-обход": "DPI bypass",
    "ДИАГНОСТИКА": "DIAGNOSTICS",
    "TLS-handshake к каждому хосту с правильным SNI. Если рукопожатие проходит — DPI-обход работает.":
        "TLS handshake to each host with the right SNI. If it completes, the DPI bypass works.",
    "идёт проверка…": "checking…",
    "  проверить ещё раз  ": "  test again  ",
    "всё проходит (": "everything passes (",
    "ничего не проходит (": "nothing passes (",
    "проходит ": "passes ",
    " из ": " of ",
    " — частичный обход": " — partial bypass",
    ") — DPI режет всё": ") — DPI blocks everything",
    ") — DPI-обход работает": ") — the DPI bypass works",
    # ── чипсы пресетов, темы, мелочи ─────────────────────────────────
    ' ИИ-сервисы ': ' AI services ',
    ' Игры и стриминг ': ' Games & streaming ',
    ' Социальные сети ': ' Social networks ',
    ' Популярное в РФ ': ' Popular in RU ',
    ' Свой набор ': ' Custom ',
    ' Светлая ': ' Light ',
    ' Тёмная ': ' Dark ',
    ' обычный ': ' normal ',
    ' гейминг ': ' gaming ',
    'Hostname по одному на строку или через ; . Попадают в list-general-user.txt zapret. Изменения применяются при следующем включении EXDPI.':
        'One hostname per line, or separated by ; . Goes into zapret list-general-user.txt. Applied on next EXDPI toggle.',
    'пусто — будет создан плейсхолдер': 'empty — a placeholder will be created',
    'Ваш собственный список доменов из поля ниже. Сохраняется отдельно от пресетов.':
        'Your own domain list from the field below. Stored separately from presets.',
    'Запускать winws.exe в фоне для обхода DPI.': 'Run winws.exe in the background for DPI bypass.',
    'Защищённый DNS (DoH/DoT)': 'Secure DNS (DoH/DoT)',
    'Локальный DNS на 127.0.0.1: запросы к провайдеру шифруются, DPI не видит и не подменяет их. Включается вместе с обходом.':
        'Local DNS on 127.0.0.1: queries are encrypted to your provider, DPI cannot see or spoof them. Enabled together with the bypass.',
    'Локальный прокси для Telegram Desktop через WebSocket.':
        'Local proxy for Telegram Desktop over WebSocket.',
}
