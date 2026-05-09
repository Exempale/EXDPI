# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec для сборки одного exe EXDPI."""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path.cwd()

datas = [
    (str(ROOT / "resources" / "icon.ico"), "resources"),
    (str(ROOT / "resources" / "icon.png"), "resources"),
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
    'app.config',
    'app.paths',
    'app.updater',
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

# cryptography — нативный _rust.pyd + бинарные зависимости
for pkg in ('cryptography',):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# Включаем все ресурсы zapret (bin + lists + bat-стратегии)
zapret_root = ROOT / "resources" / "zapret"
for path in zapret_root.rglob("*"):
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
