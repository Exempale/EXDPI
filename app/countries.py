"""Справочник стран для VPN-списка серверов: ISO-код → названия/алиасы/флаг.

Единый источник правды, который используют два места:
* ``app.singbox_config.guess_country_code`` — определяет ISO-код по тегу
  сервера в подписке (там обычно код/название/эмодзи-флаг страны);
* ``app.widgets._draw_flag`` — рисует упрощённый флаг на маленьком Canvas
  (Windows Tk не умеет показывать flag-эмодзи как иконки, поэтому рисуем сами).

Раньше эти данные были захардкожены прямо в singbox_config/widgets и
покрывали лишь ~20 стран — теперь их здесь ≈90+, и добавить новую страну
можно одной строкой в ``_DATA``.

Флаг-спека (последнее поле записи) — как рисовать:
  ("h",  [цвета...])              — горизонтальные полосы (сверху вниз);
  ("v",  [цвета...])              — вертикальные полосы (слева направо);
  ("cross", base, cross, inner)  — скандинавский крест со сдвигом влево
                                    (inner=None → без внутренней каймы);
  ("plus",  base, cross)         — центральный крест во всю ширину/высоту;
  ("special", iso)               — сложный флаг, рисуется вручную (см. _SPECIAL).

Отрисовка (``draw_flag``) намеренно не зависит от tkinter/THEME: принимает
любой объект ``canvas`` с методами ``create_rectangle/oval/polygon/line/
arc/text`` и ``delete`` — благодаря этому её можно юнит-тестировать
фейковым канвасом без дисплея.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# iso -> (ru_name, en_name, [extra_aliases], flag_spec)
_DATA: Dict[str, tuple] = {
    # ─── СНГ и соседи ────────────────────────────────────────────────
    "RU": ("Россия", "Russia", ["РФ", "RUSSIA"], ("h", ["#ffffff", "#0039a6", "#d52b1e"])),
    "UA": ("Украина", "Ukraine", [], ("h", ["#005bbb", "#ffd500"])),
    "BY": ("Беларусь", "Belarus", ["БЕЛОРУССИЯ"], ("h", ["#d22730", "#d22730", "#009a49"])),
    "KZ": ("Казахстан", "Kazakhstan", [], ("special", "KZ")),
    "MD": ("Молдова", "Moldova", ["МОЛДАВИЯ"], ("v", ["#0046ae", "#ffd200", "#cc092f"])),
    "GE": ("Грузия", "Georgia", [], ("plus", "#ffffff", "#ff0000")),
    "AM": ("Армения", "Armenia", [], ("h", ["#d90012", "#0033a0", "#f2a800"])),
    "AZ": ("Азербайджан", "Azerbaijan", [], ("h", ["#00b5e2", "#ef3340", "#509e2f"])),
    "UZ": ("Узбекистан", "Uzbekistan", [], ("h", ["#0099b5", "#ffffff", "#1eb53a"])),
    "KG": ("Киргизия", "Kyrgyzstan", ["КЫРГЫЗСТАН"], ("special", "KG")),
    "TJ": ("Таджикистан", "Tajikistan", [], ("h", ["#cc0000", "#ffffff", "#006600"])),
    "TM": ("Туркмения", "Turkmenistan", ["ТУРКМЕНИСТАН"], ("h", ["#28ae66", "#28ae66", "#28ae66"])),

    # ─── Европа ──────────────────────────────────────────────────────
    "NL": ("Нидерланды", "Netherlands", ["ГОЛЛАНДИЯ", "HOLLAND"], ("h", ["#ae1c28", "#ffffff", "#21468b"])),
    "DE": ("Германия", "Germany", [], ("h", ["#000000", "#dd0000", "#ffce00"])),
    "FR": ("Франция", "France", [], ("v", ["#0055a4", "#ffffff", "#ef4135"])),
    "GB": ("Великобритания", "United Kingdom", ["UK", "ENGLAND", "BRITAIN", "АНГЛИЯ"], ("special", "GB")),
    "FI": ("Финляндия", "Finland", [], ("cross", "#ffffff", "#003580", None)),
    "SE": ("Швеция", "Sweden", [], ("cross", "#006aa7", "#fecc00", None)),
    "NO": ("Норвегия", "Norway", [], ("cross", "#ef2b2d", "#ffffff", "#002868")),
    "DK": ("Дания", "Denmark", [], ("cross", "#c8102e", "#ffffff", None)),
    "IS": ("Исландия", "Iceland", [], ("cross", "#02529c", "#ffffff", "#dc1e35")),
    "IE": ("Ирландия", "Ireland", [], ("v", ["#169b62", "#ffffff", "#ff883e"])),
    "BE": ("Бельгия", "Belgium", [], ("v", ["#000000", "#fdda24", "#ef3340"])),
    "LU": ("Люксембург", "Luxembourg", [], ("h", ["#ed2939", "#ffffff", "#00a1de"])),
    "AT": ("Австрия", "Austria", [], ("h", ["#ed2939", "#ffffff", "#ed2939"])),
    "CH": ("Швейцария", "Switzerland", [], ("special", "CH")),
    "IT": ("Италия", "Italy", [], ("v", ["#009246", "#ffffff", "#ce2b37"])),
    "ES": ("Испания", "Spain", [], ("h", ["#aa151b", "#f1bf00", "#aa151b"])),
    "PT": ("Португалия", "Portugal", [], ("v", ["#006600", "#006600", "#ff0000"])),
    "PL": ("Польша", "Poland", [], ("h", ["#ffffff", "#dc143c"])),
    "CZ": ("Чехия", "Czechia", ["ЧЕХИЯ"], ("special", "CZ")),
    "SK": ("Словакия", "Slovakia", [], ("h", ["#ffffff", "#0b4ea2", "#ee1c25"])),
    "HU": ("Венгрия", "Hungary", [], ("h", ["#cd2a3e", "#ffffff", "#436f4d"])),
    "RO": ("Румыния", "Romania", [], ("v", ["#002b7f", "#fcd116", "#ce1126"])),
    "BG": ("Болгария", "Bulgaria", [], ("h", ["#ffffff", "#00966e", "#d62612"])),
    "GR": ("Греция", "Greece", [], ("special", "GR")),
    "HR": ("Хорватия", "Croatia", [], ("h", ["#ff0000", "#ffffff", "#171796"])),
    "SI": ("Словения", "Slovenia", [], ("h", ["#ffffff", "#0000c6", "#ff0000"])),
    "RS": ("Сербия", "Serbia", [], ("h", ["#c6363c", "#0c4076", "#ffffff"])),
    "BA": ("Босния", "Bosnia", ["БОСНИЯ"], ("h", ["#002395", "#fecb00"])),
    "MK": ("Северная Македония", "North Macedonia", ["MACEDONIA", "МАКЕДОНИЯ"], ("special", "MK")),
    "CY": ("Кипр", "Cyprus", ["КИПР"], ("special", "CY")),
    "AL": ("Албания", "Albania", [], ("h", ["#e41e20", "#e41e20"])),
    "ME": ("Черногория", "Montenegro", [], ("h", ["#c40308", "#c40308"])),
    "LT": ("Литва", "Lithuania", [], ("h", ["#fdb913", "#006a44", "#c1272d"])),
    "LV": ("Латвия", "Latvia", [], ("h", ["#9e3039", "#ffffff", "#9e3039"])),
    "EE": ("Эстония", "Estonia", [], ("h", ["#0072ce", "#000000", "#ffffff"])),
    "MT": ("Мальта", "Malta", [], ("v", ["#ffffff", "#cf142b"])),
    "MC": ("Монако", "Monaco", [], ("h", ["#ce1126", "#ffffff"])),

    # ─── Америка ─────────────────────────────────────────────────────
    "US": ("США", "United States", ["USA", "АМЕРИКА"], ("special", "US")),
    "CA": ("Канада", "Canada", [], ("special", "CA")),
    "MX": ("Мексика", "Mexico", [], ("v", ["#006847", "#ffffff", "#ce1126"])),
    "BR": ("Бразилия", "Brazil", [], ("special", "BR")),
    "AR": ("Аргентина", "Argentina", [], ("special", "AR")),
    "CL": ("Чили", "Chile", [], ("special", "CL")),
    "CO": ("Колумбия", "Colombia", [], ("h", ["#fcd116", "#003893", "#ce1126"])),
    "PE": ("Перу", "Peru", [], ("v", ["#d91023", "#ffffff", "#d91023"])),
    "VE": ("Венесуэла", "Venezuela", [], ("h", ["#ffcc00", "#00247d", "#cf142b"])),
    "EC": ("Эквадор", "Ecuador", [], ("h", ["#ffdd00", "#034ea2", "#ed1c24"])),
    "UY": ("Уругвай", "Uruguay", [], ("h", ["#ffffff", "#0038a8", "#ffffff"])),

    # ─── Азия ────────────────────────────────────────────────────────
    "JP": ("Япония", "Japan", [], ("special", "JP")),
    "KR": ("Южная Корея", "South Korea", ["КОРЕЯ", "KOREA"], ("special", "KR")),
    "CN": ("Китай", "China", [], ("special", "CN")),
    "HK": ("Гонконг", "Hong Kong", ["HONGKONG"], ("special", "HK")),
    "TW": ("Тайвань", "Taiwan", [], ("special", "TW")),
    "SG": ("Сингапур", "Singapore", [], ("h", ["#ed2939", "#ffffff"])),
    "MY": ("Малайзия", "Malaysia", [], ("special", "MY")),
    "TH": ("Таиланд", "Thailand", [], ("h", ["#a51931", "#ffffff", "#2d2a4a", "#ffffff", "#a51931"])),
    "VN": ("Вьетнам", "Vietnam", [], ("special", "VN")),
    "ID": ("Индонезия", "Indonesia", [], ("h", ["#ff0000", "#ffffff"])),
    "PH": ("Филиппины", "Philippines", [], ("special", "PH")),
    "IN": ("Индия", "India", [], ("h", ["#ff9933", "#ffffff", "#138808"])),
    "PK": ("Пакистан", "Pakistan", [], ("v", ["#ffffff", "#01411c", "#01411c", "#01411c"])),
    "BD": ("Бангладеш", "Bangladesh", [], ("special", "BD")),
    "KH": ("Камбоджа", "Cambodia", [], ("h", ["#032ea1", "#e00025", "#032ea1"])),
    "LA": ("Лаос", "Laos", [], ("h", ["#ce1126", "#002868", "#ce1126"])),
    "MM": ("Мьянма", "Myanmar", [], ("h", ["#fecb00", "#34b233", "#ea2839"])),
    "MN": ("Монголия", "Mongolia", [], ("v", ["#c4272e", "#015197", "#c4272e"])),

    # ─── Ближний Восток ──────────────────────────────────────────────
    "TR": ("Турция", "Turkey", ["ТУРЦИЯ"], ("special", "TR")),
    "IL": ("Израиль", "Israel", [], ("special", "IL")),
    "AE": ("ОАЭ", "United Arab Emirates", ["UAE"], ("special", "AE")),
    "SA": ("Саудовская Аравия", "Saudi Arabia", ["САУДОВСКАЯ"], ("h", ["#006c35", "#006c35"])),
    "QA": ("Катар", "Qatar", [], ("v", ["#ffffff", "#8a1538", "#8a1538", "#8a1538"])),
    "KW": ("Кувейт", "Kuwait", [], ("h", ["#007a3d", "#ffffff", "#ce1126"])),
    "BH": ("Бахрейн", "Bahrain", [], ("v", ["#ffffff", "#ce1126"])),
    "JO": ("Иордания", "Jordan", [], ("h", ["#000000", "#ffffff", "#007a3b"])),
    "LB": ("Ливан", "Lebanon", [], ("h", ["#ed1c24", "#ffffff", "#ed1c24"])),
    "IQ": ("Ирак", "Iraq", [], ("h", ["#ce1126", "#ffffff", "#000000"])),
    "IR": ("Иран", "Iran", [], ("h", ["#239f40", "#ffffff", "#da0000"])),

    # ─── Африка ──────────────────────────────────────────────────────
    "ZA": ("ЮАР", "South Africa", [], ("special", "ZA")),
    "EG": ("Египет", "Egypt", [], ("h", ["#ce1126", "#ffffff", "#000000"])),
    "MA": ("Марокко", "Morocco", [], ("special", "MA")),
    "DZ": ("Алжир", "Algeria", [], ("v", ["#006233", "#ffffff"])),
    "TN": ("Тунис", "Tunisia", [], ("special", "TN")),
    "NG": ("Нигерия", "Nigeria", [], ("v", ["#008751", "#ffffff", "#008751"])),
    "KE": ("Кения", "Kenya", [], ("h", ["#000000", "#bb0000", "#006600"])),
    "ET": ("Эфиопия", "Ethiopia", [], ("h", ["#078930", "#fcdd09", "#da121a"])),
    "GH": ("Гана", "Ghana", [], ("h", ["#ce1126", "#fcd116", "#006b3f"])),

    # ─── Океания ─────────────────────────────────────────────────────
    "AU": ("Австралия", "Australia", [], ("special", "AU")),
    "NZ": ("Новая Зеландия", "New Zealand", ["НОВАЯ ЗЕЛАНДИЯ"], ("special", "NZ")),
}


# ─────────────────────────────────────────────────────────────────────────────
#  Производные таблицы: код-поиск, названия, флаг-спеки
# ─────────────────────────────────────────────────────────────────────────────
def _build_lookup() -> Tuple[Dict[str, str], Dict[str, Tuple[str, str]], Dict[str, tuple]]:
    codes: Dict[str, str] = {}
    names: Dict[str, Tuple[str, str]] = {}
    specs: Dict[str, tuple] = {}
    for iso, (ru, en, aliases, spec) in _DATA.items():
        specs[iso] = spec
        names[iso] = (ru, en)
        # все варианты написания в верхнем регистре → iso
        keys = [iso, ru, en] + list(aliases)
        for k in keys:
            ku = str(k).strip().upper()
            if ku:
                codes.setdefault(ku, iso)
    return codes, names, specs


COUNTRY_CODES, NAMES, FLAG_SPECS = _build_lookup()


def display_name(code: str, lang: str = "ru") -> str:
    """Человекочитаемое имя страны по ISO-коду (``ru`` по умолчанию)."""
    pair = NAMES.get((code or "").upper())
    if not pair:
        return code
    return pair[0] if lang == "ru" else pair[1]


# ─────────────────────────────────────────────────────────────────────────────
#  Отрисовка флага (без tkinter/THEME — тестируемо фейковым канвасом)
# ─────────────────────────────────────────────────────────────────────────────
def _stripes_h(c, colors, w, h) -> None:
    n = len(colors)
    for i, col in enumerate(colors):
        c.create_rectangle(0, i * h / n, w, (i + 1) * h / n, fill=col, outline="")


def _stripes_v(c, colors, w, h) -> None:
    n = len(colors)
    for i, col in enumerate(colors):
        c.create_rectangle(i * w / n, 0, (i + 1) * w / n, h, fill=col, outline="")


def _cross(c, base, cross, inner, w, h) -> None:
    """Скандинавский крест (вертикаль сдвинута влево)."""
    c.create_rectangle(0, 0, w, h, fill=base, outline="")
    c.create_rectangle(0, h * 0.40, w, h * 0.60, fill=cross, outline="")
    c.create_rectangle(w * 0.28, 0, w * 0.44, h, fill=cross, outline="")
    if inner:
        c.create_rectangle(0, h * 0.44, w, h * 0.56, fill=inner, outline="")
        c.create_rectangle(w * 0.32, 0, w * 0.40, h, fill=inner, outline="")


def _plus(c, base, cross, w, h) -> None:
    """Центральный крест во всю ширину/высоту (Грузия, Швейцария-подобные)."""
    c.create_rectangle(0, 0, w, h, fill=base, outline="")
    c.create_rectangle(0, h * 0.40, w, h * 0.60, fill=cross, outline="")
    c.create_rectangle(w * 0.42, 0, w * 0.58, h, fill=cross, outline="")


# ── ручные (сложные) флаги: iso → функция(canvas, w, h) ──────────────────────
def _f_us(c, w, h):
    _stripes_h(c, ["#b22234", "#ffffff"] * 3 + ["#b22234"], w, h)
    c.create_rectangle(0, 0, w * 0.4, h * 0.55, fill="#3c3b6e", outline="")


def _f_gb(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#00247d", outline="")
    c.create_line(0, 0, w, h, fill="#ffffff", width=3)
    c.create_line(w, 0, 0, h, fill="#ffffff", width=3)
    c.create_rectangle(0, h * 0.40, w, h * 0.60, fill="#ffffff", outline="")
    c.create_rectangle(w * 0.42, 0, w * 0.58, h, fill="#ffffff", outline="")
    c.create_rectangle(0, h * 0.44, w, h * 0.56, fill="#cf142b", outline="")
    c.create_rectangle(w * 0.46, 0, w * 0.54, h, fill="#cf142b", outline="")


def _f_ch(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#d52b1e", outline="")
    c.create_rectangle(w * 0.42, h * 0.20, w * 0.58, h * 0.80, fill="#ffffff", outline="")
    c.create_rectangle(w * 0.25, h * 0.40, w * 0.75, h * 0.60, fill="#ffffff", outline="")


def _f_tr(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#e30a17", outline="")
    c.create_oval(w * 0.26, h * 0.22, w * 0.54, h * 0.78, fill="#ffffff", outline="")
    c.create_oval(w * 0.34, h * 0.28, w * 0.58, h * 0.72, fill="#e30a17", outline="")
    c.create_text(w * 0.62, h * 0.5, text="★", fill="#ffffff", font=("Segoe UI", 6))


def _f_jp(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#ffffff", outline="")
    c.create_oval(w * 0.32, h * 0.18, w * 0.68, h * 0.82, fill="#bc002d", outline="")


def _f_cn(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#de2910", outline="")
    c.create_text(w * 0.22, h * 0.36, text="★", fill="#ffde00", font=("Segoe UI", 9))
    c.create_text(w * 0.42, h * 0.18, text="★", fill="#ffde00", font=("Segoe UI", 4))
    c.create_text(w * 0.50, h * 0.34, text="★", fill="#ffde00", font=("Segoe UI", 4))
    c.create_text(w * 0.50, h * 0.56, text="★", fill="#ffde00", font=("Segoe UI", 4))
    c.create_text(w * 0.42, h * 0.72, text="★", fill="#ffde00", font=("Segoe UI", 4))


def _f_kr(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#ffffff", outline="")
    c.create_oval(w * 0.38, h * 0.32, w * 0.62, h * 0.68, fill="#0047a0", outline="")
    c.create_arc(w * 0.38, h * 0.32, w * 0.62, h * 0.68, start=45, extent=180,
                 fill="#cd2e3a", outline="")


def _f_ca(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#ffffff", outline="")
    c.create_rectangle(0, 0, w * 0.25, h, fill="#ff0000", outline="")
    c.create_rectangle(w * 0.75, 0, w, h, fill="#ff0000", outline="")
    c.create_text(w * 0.5, h * 0.5, text="\u2724", fill="#ff0000", font=("Segoe UI", 8))


def _f_br(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#009c3b", outline="")
    c.create_polygon(w * 0.5, h * 0.12, w * 0.9, h * 0.5, w * 0.5, h * 0.88,
                     w * 0.1, h * 0.5, fill="#ffdf00", outline="")
    c.create_oval(w * 0.38, h * 0.32, w * 0.62, h * 0.68, fill="#002776", outline="")


def _f_ar(c, w, h):
    _stripes_h(c, ["#74acdf", "#ffffff", "#74acdf"], w, h)
    c.create_oval(w * 0.44, h * 0.40, w * 0.56, h * 0.60, fill="#f6b40e", outline="")


def _f_cl(c, w, h):
    c.create_rectangle(0, 0, w, h * 0.5, fill="#ffffff", outline="")
    c.create_rectangle(0, h * 0.5, w, h, fill="#d52b1e", outline="")
    c.create_rectangle(0, 0, w * 0.34, h * 0.5, fill="#0039a6", outline="")
    c.create_text(w * 0.17, h * 0.25, text="★", fill="#ffffff", font=("Segoe UI", 6))


def _f_za(c, w, h):
    c.create_rectangle(0, 0, w, h * 0.5, fill="#e03c31", outline="")
    c.create_rectangle(0, h * 0.5, w, h, fill="#001489", outline="")
    c.create_rectangle(0, h * 0.4, w, h * 0.6, fill="#007749", outline="")
    c.create_polygon(0, 0, w * 0.4, h * 0.5, 0, h, fill="#000000", outline="")


def _f_gr(c, w, h):
    _stripes_h(c, ["#0d5eaf", "#ffffff"] * 2 + ["#0d5eaf"], w, h)
    c.create_rectangle(0, 0, w * 0.4, h * 0.55, fill="#0d5eaf", outline="")
    c.create_rectangle(0, h * 0.16, w * 0.4, h * 0.30, fill="#ffffff", outline="")
    c.create_rectangle(w * 0.13, 0, w * 0.27, h * 0.55, fill="#ffffff", outline="")


def _f_ae(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#ffffff", outline="")
    c.create_rectangle(w * 0.22, 0, w, h * 0.33, fill="#00732f", outline="")
    c.create_rectangle(w * 0.22, h * 0.66, w, h, fill="#000000", outline="")
    c.create_rectangle(0, 0, w * 0.22, h, fill="#ff0000", outline="")


def _f_il(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#ffffff", outline="")
    c.create_rectangle(0, h * 0.15, w, h * 0.28, fill="#0038b8", outline="")
    c.create_rectangle(0, h * 0.72, w, h * 0.85, fill="#0038b8", outline="")
    c.create_text(w * 0.5, h * 0.5, text="\u2721", fill="#0038b8", font=("Segoe UI", 7))


def _f_kz(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#00afca", outline="")
    c.create_oval(w * 0.40, h * 0.30, w * 0.60, h * 0.70, fill="#fec50c", outline="")


def _f_kg(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#e8112d", outline="")
    c.create_oval(w * 0.40, h * 0.30, w * 0.60, h * 0.70, fill="#ffef00", outline="")


def _f_cz(c, w, h):
    c.create_rectangle(0, 0, w, h * 0.5, fill="#ffffff", outline="")
    c.create_rectangle(0, h * 0.5, w, h, fill="#d7141a", outline="")
    c.create_polygon(0, 0, w * 0.5, h * 0.5, 0, h, fill="#11457e", outline="")


def _f_hk(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#de2910", outline="")
    c.create_oval(w * 0.38, h * 0.28, w * 0.62, h * 0.72, fill="#ffffff", outline="")


def _f_tw(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#fe0000", outline="")
    c.create_rectangle(0, 0, w * 0.5, h * 0.5, fill="#000095", outline="")
    c.create_oval(w * 0.15, h * 0.12, w * 0.35, h * 0.38, fill="#ffffff", outline="")


def _f_my(c, w, h):
    _stripes_h(c, ["#cc0001", "#ffffff"] * 3 + ["#cc0001"], w, h)
    c.create_rectangle(0, 0, w * 0.5, h * 0.55, fill="#010066", outline="")
    c.create_text(w * 0.25, h * 0.27, text="\u262a", fill="#ffcc00", font=("Segoe UI", 7))


def _f_vn(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#da251d", outline="")
    c.create_text(w * 0.5, h * 0.5, text="★", fill="#ffff00", font=("Segoe UI", 9))


def _f_ph(c, w, h):
    c.create_rectangle(0, 0, w, h * 0.5, fill="#0038a8", outline="")
    c.create_rectangle(0, h * 0.5, w, h, fill="#ce1126", outline="")
    c.create_polygon(0, 0, w * 0.45, h * 0.5, 0, h, fill="#ffffff", outline="")
    c.create_text(w * 0.14, h * 0.5, text="\u2600", fill="#fcd116", font=("Segoe UI", 6))


def _f_bd(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#006a4e", outline="")
    c.create_oval(w * 0.34, h * 0.28, w * 0.60, h * 0.72, fill="#f42a41", outline="")


def _f_ma(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#c1272d", outline="")
    c.create_text(w * 0.5, h * 0.5, text="\u2605", fill="#006233", font=("Segoe UI", 9))


def _f_tn(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#e70013", outline="")
    c.create_oval(w * 0.36, h * 0.20, w * 0.64, h * 0.80, fill="#ffffff", outline="")
    c.create_text(w * 0.5, h * 0.5, text="\u262a", fill="#e70013", font=("Segoe UI", 7))


def _f_au(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#00008b", outline="")
    c.create_rectangle(0, 0, w * 0.5, h * 0.5, fill="#00247d", outline="")
    c.create_text(w * 0.25, h * 0.25, text="\u271a", fill="#ffffff", font=("Segoe UI", 7))
    c.create_text(w * 0.75, h * 0.6, text="★", fill="#ffffff", font=("Segoe UI", 7))


def _f_nz(c, w, h):
    c.create_rectangle(0, 0, w, h, fill="#00247d", outline="")
    c.create_rectangle(0, 0, w * 0.5, h * 0.5, fill="#012169", outline="")
    c.create_line(0, 0, w * 0.5, h * 0.5, fill="#ffffff", width=2)
    c.create_line(w * 0.5, 0, 0, h * 0.5, fill="#ffffff", width=2)
    c.create_text(w * 0.72, h * 0.35, text="★", fill="#cc142b", font=("Segoe UI", 5))
    c.create_text(w * 0.82, h * 0.65, text="★", fill="#cc142b", font=("Segoe UI", 5))


def _f_mk(c, w, h):
    # Красное поле + жёлтое солнце с лучами (упрощённо).
    c.create_rectangle(0, 0, w, h, fill="#d20000", outline="")
    cx, cy = w * 0.5, h * 0.5
    for pts in (
        (0, 0, cx, cy, 0, h * 0.30),
        (w, 0, cx, cy, w, h * 0.30),
        (0, h, cx, cy, 0, h * 0.70),
        (w, h, cx, cy, w, h * 0.70),
        (cx - w * 0.12, 0, cx, cy, cx + w * 0.12, 0),
        (cx - w * 0.12, h, cx, cy, cx + w * 0.12, h),
        (0, cy - h * 0.12, cx, cy, 0, cy + h * 0.12),
        (w, cy - h * 0.12, cx, cy, w, cy + h * 0.12),
    ):
        c.create_polygon(*pts, fill="#f8c300", outline="")
    c.create_oval(cx - w * 0.17, cy - h * 0.24, cx + w * 0.17, cy + h * 0.24,
                  fill="#f8c300", outline="#d20000")


def _f_cy(c, w, h):
    # Белое поле + медный силуэт острова + две оливковые ветви.
    c.create_rectangle(0, 0, w, h, fill="#ffffff", outline="")
    c.create_polygon(
        w * 0.30, h * 0.40, w * 0.55, h * 0.33, w * 0.70, h * 0.40,
        w * 0.66, h * 0.50, w * 0.48, h * 0.54, w * 0.34, h * 0.50,
        fill="#d57800", outline="",
    )
    c.create_line(w * 0.44, h * 0.58, w * 0.50, h * 0.70, fill="#3a7728", width=1)
    c.create_line(w * 0.56, h * 0.58, w * 0.50, h * 0.70, fill="#3a7728", width=1)


_SPECIAL = {
    "US": _f_us, "GB": _f_gb, "CH": _f_ch, "TR": _f_tr, "JP": _f_jp, "CN": _f_cn,
    "KR": _f_kr, "CA": _f_ca, "BR": _f_br, "AR": _f_ar, "CL": _f_cl, "ZA": _f_za,
    "GR": _f_gr, "AE": _f_ae, "IL": _f_il, "KZ": _f_kz, "KG": _f_kg, "CZ": _f_cz,
    "HK": _f_hk, "TW": _f_tw, "MY": _f_my, "VN": _f_vn, "PH": _f_ph, "BD": _f_bd,
    "MA": _f_ma, "TN": _f_tn, "AU": _f_au, "NZ": _f_nz,
    "MK": _f_mk, "CY": _f_cy,
}


def draw_flag(canvas, code: str, w: int, h: int,
              fallback_bg: str = "#1F2832", fallback_fg: str = "#7B8794") -> None:
    """Нарисовать упрощённый флаг страны ``code`` на ``canvas`` размера ``w×h``.

    Если код неизвестен — серый прямоугольник с двухбуквенным кодом.
    """
    canvas.delete("all")
    spec = FLAG_SPECS.get((code or "").upper())
    if spec is None:
        canvas.create_rectangle(0, 0, w, h, fill=fallback_bg, outline="")
        canvas.create_text(w / 2, h / 2, text=(code or "")[:2],
                           fill=fallback_fg, font=("Segoe UI", 6, "bold"))
        return
    kind = spec[0]
    if kind == "h":
        _stripes_h(canvas, spec[1], w, h)
    elif kind == "v":
        _stripes_v(canvas, spec[1], w, h)
    elif kind == "cross":
        _cross(canvas, spec[1], spec[2], spec[3] if len(spec) > 3 else None, w, h)
    elif kind == "plus":
        _plus(canvas, spec[1], spec[2], w, h)
    elif kind == "special":
        drawer = _SPECIAL.get(spec[1])
        if drawer is not None:
            drawer(canvas, w, h)
        else:
            canvas.create_rectangle(0, 0, w, h, fill=fallback_bg, outline="")