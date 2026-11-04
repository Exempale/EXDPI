# -*- coding: utf-8 -*-
"""Проверка целостности zapret-бандла: каждая стратегия должна ссылаться
только на файлы, которые реально лежат в бандле.

Гоняется в CI перед сборкой: если новая стратегия из апстрима ссылается
на фингерпринт, которого нет в bin/ — сборка падает сразу, а не у
пользователей с загадочным rc=1 (реальный кейс 3.2.0: ACTIVE_DISCORD_UDP.bin).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZAPRET = ROOT / "resources" / "zapret"

needed: set = set()
for bat in ZAPRET.glob("general*.bat"):
    text = bat.read_text(encoding="utf-8", errors="replace")
    for m in re.findall(r'%BIN%[\\/]*([\w.\-]+\.(?:bin|txt))', text):
        needed.add(m)

have = {p.name for p in (ZAPRET / "bin").iterdir() if p.is_file()}
have |= {p.name for p in (ZAPRET / "lists").iterdir() if p.is_file()}

missing = sorted(n for n in needed if n not in have)
if missing:
    print("ОШИБКА: стратегии ссылаются на отсутствующие файлы:")
    for name in missing:
        print("  -", name)
    print("Докладите их в resources/zapret/bin/ из бандла апстрима.")
    sys.exit(1)

print(f"bundle OK: {len(needed)} зависимостей стратегий на месте")
