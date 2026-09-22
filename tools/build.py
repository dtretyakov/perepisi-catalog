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
# Опись в ГИС УИАД — постоянная страница каталога. Опись при этом бывает разбита
# на ТОМА, и каждый том — отдельная страница со своим набором дел: у ф.214 оп.1
# том 1 кончается на деле 293, у ф.350 оп.2 тома разделены не по номерам, а по
# ревизиям. Поэтому у каждой записи стоит проверка, покрывает ли этот том данное
# дело. Без неё читатель, ищущий дело 697, попадал бы в опись, где его нет, —
# ссылка формально живая и по сути ложная.
OPIS_UIAD = {
    ("РГАДА", "214", "1"): (
        "https://online.archives.ru/guide/10000000001014/10000000161014/10000005259014/",
        lambda n: n is not None and n <= 293,   # том 1; выше — другие тома, их id не выписаны
    ),
    ("РГАДА", "350", "2"): (
        "https://online.archives.ru/guide/10000000001014/10000000297014/10000003363014/",
        lambda n: n in (149, 150),              # том 1; проверено по адресам самих дел
    ),
}


# Каталог ГИС УИАД адресуется по уровням: архив / фонд / опись / дело. Работают
# три нижних; АРХИВНЫЙ УРОВЕНЬ СЛОМАН — `/guide/10000000001014/` отдаёт 200 и
# текст «К сожалению, произошла ошибку», и ссылаться туда нельзя. Уровень фонда
# и описи живые, хотя сервер отвечает 404 примерно через раз: это его норма, а
# не признак неверного адреса.
FOND_UIAD = {
    ("РГАДА", "214"): "https://online.archives.ru/guide/10000000001014/10000000161014/",
    ("РГАДА", "350"): "https://online.archives.ru/guide/10000000001014/10000000297014/",
}

OPIS_FALLBACK = {
    "ГАПК": ("archives.permkrai.ru", "https://archives.permkrai.ru/archive/search?in=units"),
    "ГАСО": ("metriki.gaso-ural.ru", "https://metriki.gaso-ural.ru/"),
}


# Насколько можно доверять машинному чтению — одним знаком.
#
# Мера зависит от того, как устроено дело. В сплошном тексте работает плотность:
# на своей руке модель даёт двадцать четыре знака на строку и выше, ниже
# восемнадцати начинается шум. В табличном деле плотность бессмысленна — имя,
# отчество и возраст стоят в разных клетках, и даже безупречное чтение даёт
# восемь знаков на строку, — там мерой служит средняя уверенность.
#
# Когда известны обе величины, берётся худшая: д.1508 читается на тридцати трёх
# знаках, но с уверенностью 0,88, и зелёным её называть нельзя.
def grade(c):
    marks = []
    if c.get("htr") and not c.get("tabular"):
        d = float(c["htr"])
        marks.append(2 if d >= 24 else 1 if d >= 18 else 0)
    if c.get("htr_conf"):
        q = float(c["htr_conf"])
        marks.append(2 if q >= 0.95 else 1 if q >= 0.90 else 0)
    if not marks:
        return None
    mark = ["🟥", "🟨", "🟩"][min(marks)]
    conf = c["htr_conf"].replace(".", ",") if c.get("htr_conf") else None
    if c.get("tabular"):
        return f"{mark} уверенность {conf}"
    dens = f"{c['htr'].replace('.', ',')} зн/стр"
    # Когда цвет задан уверенностью, а не плотностью, одна плотность в ячейке
    # выглядит противоречием: тридцать три знака на строку и красный квадрат.
    # Тогда печатаются обе величины, и видно, которая тянет вниз.
    if conf and len(marks) == 2 and marks[1] < marks[0]:
        return f"{mark} {dens}, уверенность {conf}"
    return f"{mark} {dens}"

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


# В таблице состояние — одно слово: столбец служит для беглого просмотра, а не
# для чтения. Всё, что к нему прилагается, живёт в карточке дела.
STATE_MARK = {
    "набрана": "🟢 набрана",
    "частично набрана": "🟡 частично",
    "только машинное чтение": "🔵 распознана",
    "только образы": "⚪ образы",
    "только опись": "⚫ опись",
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


def verdict(c):
    """Полная мера для карточки: обе величины и чем задан цвет.

    В таблице стоит один квадрат, и на табличном деле он выглядит загадкой:
    зелёный при десяти знаках на строку. Карточка обязана сказать, по какой
    величине выставлен цвет и почему вторая здесь не в счёт.
    """
    g = grade(c)
    if not g:
        return None
    mark = g[0]
    dens = f"{c['htr'].replace('.', ',')} знака на строку" if c.get("htr") else None
    conf = c["htr_conf"].replace(".", ",") if c.get("htr_conf") else None
    if c.get("tabular"):
        return (f"{mark} уверенность {conf}. Плотность {dens} — величина здесь "
                "обманчивая: дело табличное, имя, отчество и возраст стоят в "
                "разных клетках, и даже безупречное чтение даёт около десяти "
                "знаков. Цвет выставлен по уверенности")
    if conf:
        return (f"{mark} {dens}, уверенность {conf}. Цвет — по худшей из двух "
                "величин")
    return f"{mark} {dens}"


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
    # Адрес описи получается из адреса дела отбрасыванием последнего сегмента —
    # это точно по построению, и никаких таблиц томов не нужно: опись, в которой
    # дело лежит, по определению та, через которую к нему пришли.
    uiad = OPIS_UIAD.get((c["arch"], c["f"], c["o"]))
    fond = FOND_UIAD.get((c["arch"], c["f"]))
    number = int(c["d"]) if c["d"].isdigit() else None
    if c.get("case_url"):
        parent = c["case_url"].rstrip("/").rsplit("/", 1)[0] + "/"
        bits.append(f"[ф.{c['f']} оп.{c['o']} в ГИС УИАД]({parent})")
    elif uiad and uiad[1](number):
        bits.append(f"[ф.{c['f']} оп.{c['o']} в ГИС УИАД]({uiad[0]})")
    elif fond:
        bits.append(f"[ф.{c['f']} в ГИС УИАД]({fond})")
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
            f"| Машинное чтение | {where}модель «{c['htr_model']}» |"
        )
        v = verdict(c)
        if v:
            lines.append(f"| Чего стоит чтение | {v} |")
    lines.append("")
    if c.get("note"):
        lines.append(c["note"])
        lines.append("")
    if c.get("htr"):
        lines.append(
            "> Машинное чтение не является транскрипцией. На этой руке модель ошибается "
            "примерно в каждом третьем знаке и способна дать связный, но неверный "
            "текст. Пригодно для поиска страницы по корню слова; для цитирования "
            "непригодно."
        )
        lines.append("")
    lines.append("[← назад в каталог](../CATALOG.md) · [о правах](../rights.md)")
    return "\n".join(lines) + "\n"


def state_cell(c):
    """Состояние одним словом; у распознанных — ещё знак качества, без чисел."""
    cell = STATE_MARK.get(c["state"], c["state"])
    g = grade(c)
    return f"{cell} {g[0]}" if g else cell


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
            f"| {state_cell(c)} | {t} |"
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
