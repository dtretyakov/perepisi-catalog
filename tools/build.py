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

# Куда вести читателя за описью. Ссылка идёт на входную страницу поиска, а не на
# конкретный PDF: у РГАДА `opisi/` — пустая заглушка, а `poisk/` — живое меню, где
# опись выбирается по фонду. Глубокие адреса просмотрщика здесь не место: они
# привязаны к сессии и годятся не для ссылки, а для выкачивания.
OPIS_URL = {
    "РГАДА": ("rgada.info/poisk", "http://rgada.info/poisk/"),
    "ГАПК": ("archives.permkrai.ru", "https://archives.permkrai.ru/archive/search?in=units"),
    "ГАСО": ("metriki.gaso-ural.ru", "https://metriki.gaso-ural.ru/"),
}

# Описи, набранные волонтёрами: читаются без входа и без оплаты.
VELIKIE = ("Великие описи", "https://inv.velikie.org/")


STATE_MARK = {
    "набрана": "🟢 набрана",
    "частично набрана": "🟡 набрана частично",
    "только машинное чтение": "🔵 машинное чтение",
    "только образы": "⚪ только образы",
    "только опись": "⚫ только опись",
}


def cipher(c):
    return f"ф.{c['f']} оп.{c['o']} д.{c['d']}"


def card(c):
    lines = [f"# {c['arch']} {cipher(c)}", ""]
    lines.append(f"**{c['title']}**")
    lines.append("")
    lines.append(f"| | |")
    lines.append(f"|---|---|")
    lines.append(f"| Годы | {c['years'] or '—'} |")
    lines.append(f"| Состояние | {STATE_MARK.get(c['state'], c['state'])} |")
    lines.append(f"| Образы | {c['scans'] or '—'} |")
    op = OPIS_URL.get(c["arch"])
    if op or c.get("opis"):
        bits = []
        if c.get("opis"):
            bits.append(c["opis"])
        if op:
            bits.append(f"[{op[0]}]({op[1]})")
        bits.append(f"[{VELIKIE[0]}]({VELIKIE[1]})")
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
           "| Шифр | Годы | Состояние | Текст | Заголовок |",
           "|---|---|---|---|---|"]
    for c in rows:
        if c.get("set") and c.get("set_url"):
            s = f"[{c['set']}]({c['set_url']})"
        elif (ROOT / "text" / f"{c['id']}.md").exists():
            s = f"[читать](text/{c['id']}.md)"
        else:
            s = c.get("set") or "—"
        t = c["title"]
        t = t[:70] + "…" if len(t) > 71 else t
        out.append(
            f"| [{c['arch']} {cipher(c)}](cases/{c['id']}.md) | {c['years'] or '—'} "
            f"| {STATE_MARK.get(c['state'], c['state'])} | {s} | {t} |"
        )
    out += ["",
            "Ресурсы, откуда всё это берётся, — в [sources.md](sources.md); "
            "что здесь можно публиковать и почему — в [rights.md](rights.md)."]
    return "\n".join(out) + "\n"


def main():
    (ROOT / "cases").mkdir(exist_ok=True)
    for c in CASES:
        (ROOT / "cases" / f"{c['id']}.md").write_text(card(c), encoding="utf-8")
    (ROOT / "CATALOG.md").write_text(catalog(), encoding="utf-8")
    print(f"карточек {len(CASES)}, каталог собран")


if __name__ == "__main__":
    main()
