#!/usr/bin/env python3
"""Собрать CATALOG.md и карточки дел из tools/cases.json.

Карточка отвечает на один вопрос, ради которого исследователь сюда пришёл:
стоит ли платить за доступ к этому делу — или его уже набрали.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = json.loads((ROOT / "tools" / "cases.json").read_text(encoding="utf-8"))

# Опись в ГИС УИАД — это отдельная страница каталога, и её адрес постоянный:
# РГАДА / фонд / опись, а дело — ещё один сегмент на конце. Это карточка, а не
# образ: открывается ссылкой и живёт годами, в отличие от подписанного адреса
# картинки, который действует минуты. Поэтому ссылаемся сюда, а не на rgada.info,
# где `opisi/` отдаёт пустую заглушку.
OPIS_UIAD = {
    ("РГАДА", "214", "1"): "https://online.archives.ru/guide/10000000001014/10000000161014/10000005259014/",
    ("РГАДА", "350", "2"): "https://online.archives.ru/guide/10000000001014/10000000297014/10000003363014/",
}

# Куда вести, когда постоянного адреса описи у нас нет.
OPIS_FALLBACK = {
    "РГАДА": ("поиск РГАДА", "http://rgada.info/poisk/"),
    "ГАПК": ("archives.permkrai.ru", "https://archives.permkrai.ru/archive/search?in=units"),
    "ГАСО": ("metriki.gaso-ural.ru", "https://metriki.gaso-ural.ru/"),
}

# Описи, набранные волонтёрами: читаются без входа и без оплаты. Страница есть
# на каждый фонд (`/archive/<архив>/<фонд>/`), а на опись — нет: адрес с номером
# описи отдаёт 404. Поэтому ведём на фонд. Пермского края у них нет вовсе, и
# ссылки для ГАПК не будет — пустая ссылка хуже её отсутствия.
VELIKIE_SLUG = {"РГАДА": "rgada", "ГАСО": "gaso-ural"}


def velikie(c):
    slug = VELIKIE_SLUG.get(c["arch"])
    if not slug:
        return None
    return f"[Великие описи](https://inv.velikie.org/archive/{slug}/{c['f']}/)"


STATE_MARK = {
    "набрана": "🟢 набрана",
    "частично набрана": "🟡 набрана частично",
    "только машинное чтение": "🔵 машинное чтение",
    "только образы": "⚪ только образы",
    "только опись": "⚫ только опись",
}


def cipher(c):
    return f"ф.{c['f']} оп.{c['o']} д.{c['d']}"


def volume(c):
    """Сколько в деле листов и образов — и откуда это известно.

    Опись считает ЛИСТЫ, просмотрщик отдаёт ОБРАЗЫ, и это разные числа: дело,
    снятое по стороне, даёт вдвое больше кадров, чем листов, а снятое
    разворотами — примерно столько же. Читателю нужны оба, иначе «358 листов»
    в описи и семьсот кадров в окне выглядят разными делами.

    Где опись листов не даёт, номер листа берётся из имени файла образа и
    диапазон считается по нему. Такое число помечается прямо в строке: это
    наш счёт, а не архивный.
    """
    bits = []
    if c.get("leaves"):
        src = "по описи" if c.get("leaves_src") == "опись" else "сосчитано по образам"
        bits.append(f"листов {c['leaves']} ({src})")
    if c.get("leaf_range"):
        bits.append(f"нумерация листов {c['leaf_range']}")
    if c.get("images"):
        bits.append(f"образов {c['images']}")
    if c.get("shot"):
        bits.append(f"снято {c['shot']}")
    return " · ".join(bits)


def card(c):
    lines = [f"# {c['arch']} {cipher(c)}", ""]
    lines.append(f"**{c['title']}**")
    lines.append("")
    lines.append(f"| | |")
    lines.append(f"|---|---|")
    lines.append(f"| Годы | {c['years'] or '—'} |")
    lines.append(f"| Состояние | {STATE_MARK.get(c['state'], c['state'])} |")
    lines.append(f"| Образы | {c['scans'] or '—'} |")
    vol = volume(c)
    if vol:
        lines.append(f"| Объём | {vol} |")
    if c.get("case_url"):
        lines.append(f"| Дело в каталоге | [ГИС УИАД]({c['case_url']}) |")
    bits = []
    if c.get("opis"):
        bits.append(c["opis"])
    uiad = OPIS_UIAD.get((c["arch"], c["f"], c["o"]))
    if uiad:
        bits.append(f"[ф.{c['f']} оп.{c['o']} в ГИС УИАД]({uiad})")
    else:
        fb = OPIS_FALLBACK.get(c["arch"])
        if fb:
            bits.append(f"[{fb[0]}]({fb[1]})")
    v = velikie(c)
    if v:
        bits.append(v)
    lines.append(f"| Опись | {' · '.join(bits)} |")
    if c.get("unit"):
        lines.append(
            f"| Дело в просмотрщике | [unit {c['unit']}]"
            f"(https://archives.permkrai.ru/archive/search?in=units&q={c['d']}) |"
        )
    if c.get("set"):
        url = f"[{c['set']}]({c['set_url']})" if c.get("set_url") else c["set"]
        lines.append(f"| Набор | {url} |")
    if c.get("htr"):
        here = (ROOT / "text" / f"{c['id']}.md").exists()
        where = f"[текст](../text/{c['id']}.md), " if here else ""
        lines.append(
            f"| Машинное чтение | {where}{c['htr']} знака на строку, "
            f"модель «{c['htr_model']}» |"
        )
    lines.append("")
    if c.get("note"):
        lines.append(c["note"])
        lines.append("")
    if c.get("htr"):
        lines.append(
            "> Машинное чтение — не транскрипция. На этой руке модель ошибается "
            "в каждом третьем знаке и охотно сочиняет правдоподобное. Годится, "
            "чтобы найти страницу по корню слова; не годится, чтобы цитировать."
        )
        lines.append("")
    lines.append("[← назад в каталог](../CATALOG.md) · [о правах](../rights.md)")
    return "\n".join(lines) + "\n"


def catalog():
    order = ["набрана", "частично набрана", "только машинное чтение", "только образы", "только опись"]
    rows = sorted(CASES, key=lambda c: (order.index(c["state"]) if c["state"] in order else 9,
                                        c["f"], c["o"], c["d"]))
    out = ["# Каталог дел", "",
           "Что уже набрано людьми, что читается только машиной, а что лежит одними образами.",
           "",
           "| Шифр | Годы | Состояние | Заголовок |",
           "|---|---|---|---|"]
    for c in rows:
        t = c["title"]
        t = t[:70] + "…" if len(t) > 71 else t
        out.append(
            f"| [{c['arch']} {cipher(c)}](cases/{c['id']}.md) | {c['years'] or '—'} "
            f"| {STATE_MARK.get(c['state'], c['state'])} | {t} |"
        )
    out += ["",
            "Ресурсы, откуда всё это берётся, — в [sources.md](sources.md); "
            "что здесь можно публиковать и почему — в [rights.md](rights.md)."]
    return "\n".join(out) + "\n"


def check(c):
    """Сходится ли счёт листов с нумерацией — сторож против тихой ошибки.

    Число листов вынималось из примечания регулярным выражением, и однажды
    оно поймало «на пробе в 25 листов» и подписало этим делом в тысячу шестьсот
    листов. Ошибка не видна глазом: строка выглядит правдоподобно. Если известны
    и число, и диапазон, они обязаны сходиться.
    """
    if not (c.get("leaves") and c.get("leaf_range")):
        return None
    lo, hi = (int(x) for x in c["leaf_range"].replace("–", "-").split("-"))
    span = hi - lo + 1
    if abs(span - c["leaves"]) > max(20, 0.15 * span):
        return (f"{c['id']}: листов {c['leaves']}, а нумерация {c['leaf_range']} "
                f"даёт {span}")
    return None


def main():
    (ROOT / "cases").mkdir(exist_ok=True)
    warn = [w for w in (check(c) for c in CASES) if w]
    for c in CASES:
        (ROOT / "cases" / f"{c['id']}.md").write_text(card(c), encoding="utf-8")
    (ROOT / "CATALOG.md").write_text(catalog(), encoding="utf-8")
    print(f"карточек {len(CASES)}, каталог собран")
    for w in warn:
        print("  ПРОВЕРЬТЕ:", w)


if __name__ == "__main__":
    main()
