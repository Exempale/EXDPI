# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec для сборки одного exe EXDPI."""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path.cwd()

datas = [
    (str(ROOT / "resources" / "icon.ico"), "resources"),
    (str(ROOT / "resources" / "icon.png"), "resources"),
    # пасхалка — прикольная картинка, открывается 5 кликами по версии
    (str(ROOT / "resources" / "easter" / "1.jpg"), "resources/easter"),
]
binaries = []
hiddenimports = [
    'pyperclip',
    'app',
    'app.controller',
    'app.proxy_runner',
    'app.zapret_runner',
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
    'pystray._win32',
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

# Включаем все ресурсы zapret (bin + lists + bat-стратегии)
zapret_root = ROOT / "resources" / "zapret"
for path in zapret_root.rglob("*"):
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
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
    icon=str(ROOT / "resources" / "icon.ico"),
    uac_admin=True,
    manifest=str(ROOT / "manifest.xml"),
    version=str(ROOT / "version_info.txt"),
)
