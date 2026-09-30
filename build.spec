# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec для сборки EXDPI: exe на Windows, бинарь на macOS.

На macOS бандлим только VPN-часть: zapret (winws + WinDivert) — виндовая
технология, его ресурсы туда не пакуем. Ядро sing-box для darwin CI
кладёт в resources/singbox/ перед сборкой.
"""
import sys

from pathlib import Path

IS_MAC = sys.platform == "darwin"

from PyInstaller.utils.hooks import collect_all

ROOT = Path.cwd()

datas = [
    (str(ROOT / "resources" / "icon.ico"), "resources"),
    (str(ROOT / "resources" / "icon.png"), "resources"),
    # пасхалка — прикольная картинка, открывается 5 кликами по версии
    (str(ROOT / "resources" / "easter" / "1.jpg"), "resources/easter"),
    # рекламные баннеры VPN-режима (app/widgets.AdBanner) — выбираются по теме
    (str(ROOT / "resources" / "banner_dark.png"), "resources"),
    (str(ROOT / "resources" / "banner_light.png"), "resources"),
]
binaries = []
hiddenimports = [
    'pyperclip',
    'app',
    'app.controller',
    'app.proxy_runner',
    'app.zapret_runner',
    'app.singbox_config',
    'app.singbox_runner',
    'app.theme',
    'app.widgets',
    'app.ui_app',
    'app.ui_settings',
    'app.ui_tg_guide',
    'app.easter',
    'app.presets',
    'app.config',
    'app.paths',
    'app.updater',
    'app.autostart',
    'app.dpi_test',
    'app.ui_dpitest',
    'app.tray',
    'pystray',
    *(() if IS_MAC else ('pystray._win32',)),
    *(() if not IS_MAC else ('pystray._darwin',)),
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageTk',
    'proxy',
    'proxy.bridge',
    'proxy.balancer',
    'proxy.config',
    'proxy.fake_tls',
    'proxy.raw_websocket',
    'proxy.stats',
    'proxy.tg_ws_proxy',
    'proxy.utils',
]

# cryptography — нативный _rust.pyd + бинарные зависимости.
# pystray — иначе теряются windows-специфичные подмодули (трей-иконка не работает).
# PIL — нужен pystray для отрисовки иконки.
for pkg in ('cryptography', 'pystray', 'PIL'):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception as exc:
        print(f"[build.spec] WARNING: collect_all({pkg}) failed: {exc}")

# Включаем все ресурсы zapret (bin + lists + bat-стратегии) — только на
# Windows: на macOS winws.exe бесполезен, 40+ МБ не тащим
if not IS_MAC:
    zapret_root = ROOT / "resources" / "zapret"
    for path in zapret_root.rglob("*"):
        if path.is_file():
            rel_dir = path.parent.relative_to(ROOT)
            datas.append((str(path), str(rel_dir)))

# Ядро Sing-box (resources/singbox/sing-box.exe) для VPN-режима (TUN).
singbox_root = ROOT / "resources" / "singbox"
for path in singbox_root.rglob("*"):
    if path.is_file():
        rel_dir = path.parent.relative_to(ROOT)
        datas.append((str(path), str(rel_dir)))

# Пресеты доменов для быстрого переключения «готовых конфиг-листов»
blocklists_root = ROOT / "blocklists"
if blocklists_root.is_dir():
    for path in blocklists_root.rglob("*"):
        if path.is_file():
            rel_dir = path.parent.relative_to(ROOT)
            datas.append((str(path), str(rel_dir)))


a = Analysis(
    ['main.py'],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter.test',
        'unittest',
        'pydoc_data',
        'test',
        'pip',
        'setuptools',
    ],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe_kwargs = dict(
    name='EXDPI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
if not IS_MAC:
    exe_kwargs['icon'] = str(ROOT / "resources" / "icon.ico")
    exe_kwargs['uac_admin'] = True
    exe_kwargs['manifest'] = str(ROOT / "manifest.xml")
    exe_kwargs['version'] = str(ROOT / "version_info.txt")

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    **exe_kwargs,
)
