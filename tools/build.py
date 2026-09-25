#!/usr/bin/env python3
"""Собрать CATALOG.md и карточки дел из tools/cases.json.

Карточка отвечает на один вопрос, ради которого исследователь сюда пришёл:
стоит ли платить за доступ к этому делу — или его уже набрали.
"""
import json
import os
from pathlib import Path

import geo
import search_index
from models import model_link, model_url

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
# Номера в списках — те дела, для которых адрес описи проверен по адресу самого
# дела: средний сегмент его ссылки и есть опись. Ф.350 оп.2 сперва считалась
# разбитой на тома, и список держали в двух номерах; затем под тем же адресом
# описи открылись дела от 149 до 1614, то есть страница покрывает опись целиком.
# Список тем не менее остаётся перечнем проверенного, а не «все дела подряд»:
# каталог не утверждает того, чего не открывал.
OPIS_UIAD = {
    ("РГАДА", "214", "1"): (
        "https://online.archives.ru/guide/10000000001014/10000000161014/10000005259014/",
        lambda n: n is not None and n <= 293,   # том 1; выше — другие тома, их id не выписаны
    ),
    ("РГАДА", "350", "1"): (
        "https://online.archives.ru/guide/10000000001014/10000000297014/10000005244014/",
        lambda n: n in (51, 178, 213),
    ),
    ("РГАДА", "350", "2"): (
        "https://online.archives.ru/guide/10000000001014/10000000297014/10000003363014/",
        lambda n: n in (149, 150, 901, 910, 1340, 1342, 1343, 1606, 1607, 1608, 1611, 1614, 1620, 1621, 1622),
    ),
    ("РГАДА", "1209", "1"): (
        "https://online.archives.ru/guide/10000000001014/10000001151014/10000005098014/",
        lambda n: n in (44, 185, 186, 351, 442, 518, 519),
    ),
}


# Каталог ГИС УИАД адресуется по уровням: архив / фонд / опись / дело. Работают
# три нижних; АРХИВНЫЙ УРОВЕНЬ СЛОМАН — `/guide/10000000001014/` отдаёт 200 и
# текст «К сожалению, произошла ошибку», и ссылаться туда нельзя. Уровень фонда
# и описи живые, хотя сервер отвечает 404 примерно через раз: это его норма, а
# не признак неверного адреса.
# Идентификаторы фондов сняты со списка `/guide/<архив>/all_fund/` — того самого,
# который по адресу `/guide/<архив>/` отдаёт ошибку. Список работает, ошибается
# только короткий адрес.
_G = "https://online.archives.ru/guide/10000000001014/"
FOND_UIAD = {
    ("РГАДА", "214"): _G + "10000000161014/",
    ("РГАДА", "281"): _G + "10000000228014/",
    ("РГАДА", "350"): _G + "10000000297014/",
    ("РГАДА", "1111"): _G + "10000001053014/",
    ("РГАДА", "1209"): _G + "10000001151014/",
    ("РГАДА", "1455"): _G + "10000001391014/",
    ("РГАДА", "1642"): _G + "10000001482014/",
}

# У ГАПК в адресе стоит номер архивного учреждения: `/archive1/`, а не `/archive/`.
# Само дело — `/archive1/unit/<unit>`, опись — `/archive1/inventory/73643`
# (ф.111 оп.1), фонд — `/archive1/funds/73621`. Поиск живёт по параметру `search`,
# а не `q`: с `q` страница отвечает 200 и печатает «Ничего не найдено».
GAPK = "https://archives.permkrai.ru/archive1/"

OPIS_FALLBACK = {
    "ГАПК": ("ф.111 оп.1 в каталоге ГАПК", GAPK + "inventory/73643"),
    "ГАСО": ("metriki.gaso-ural.ru", "https://metriki.gaso-ural.ru/"),
}


# Насколько можно доверять машинному чтению — одним знаком.
#
# Величин две, и поодиночке каждая обманывает. Плотность знаков на строку
# показывает, берёт ли модель руку вообще: на своей руке она даёт под тридцать,
# ниже двенадцати идёт чистый шум. Но на табличном деле плотность падает не от
# плохого чтения, а от устройства листа: имя, отчество и возраст стоят в разных
# клетках, и безупречное чтение даёт около десяти знаков. Уверенность же — это
# число модели о самой себе, и на чужой руке она держится высокой под полной
# бессмыслицей: на скорописи 1632 года чужая модель выдаёт вымысел при 0,99.
#
# Поэтому обе приводятся к доле от достижимого — своей для сплошного дела и
# своей для табличного — и сводятся СРЕДНИМ ГЕОМЕТРИЧЕСКИМ. Оно выбрано не для
# красоты: среднее арифметическое позволяет одной хорошей величине вытянуть
# другую, провальную, а геометрическое — нет. Тридцать три знака на строку при
# уверенности 0,88 зелёного не дают, и это правильно: густой текст, в котором
# модель сама не уверена, для поиска годится хуже, чем кажется.
NOISE_FLOOR = {False: 12.0, True: 4.0}     # ниже этого плотность — шум
GOOD_DENSITY = {False: 28.0, True: 10.0}   # выше этого прибавки нет
CONF_FLOOR, CONF_GOOD = 0.80, 0.96


def clamp(x):
    return max(0.0, min(1.0, x))


def score(c):
    """Композитная оценка чтения долей единицы, либо None."""
    tabular = bool(c.get("tabular"))
    parts = []
    if c.get("htr"):
        lo, hi = NOISE_FLOOR[tabular], GOOD_DENSITY[tabular]
        parts.append(clamp((float(c["htr"]) - lo) / (hi - lo)))
    if c.get("htr_conf"):
        parts.append(clamp((float(c["htr_conf"]) - CONF_FLOOR) / (CONF_GOOD - CONF_FLOOR)))
    if not parts:
        return None
    product = 1.0
    for x in parts:
        product *= x
    return product ** (1.0 / len(parts))


def mark_of(x):
    return "🟩" if x >= 0.75 else "🟨" if x >= 0.45 else "🟥"


# Плотность и уверенность говорят, берёт ли модель руку, но не то, сколько знаков
# она читает верно. После восьмой версии плотность у всех дел поднялась под тридцать,
# и одна плотность ставила зелёное всему подряд — в том числе Кромам 1748 года, где
# на размеченных вручную строках верных знаков 61 %. Поэтому знак ограничен сверху
# тем, что модель показала на книгах ТОГО ЖЕ ВРЕМЕНИ, а если размечено само дело —
# им. Мерки — версии 8 (сентябрь 2026); более ранние версии читают не лучше, так что
# для их чтений это тоже верхняя граница.
MEASURED = {  # дело → доля верных знаков на размеченных вручную строках этого дела
    "rgada-350-2-1620": 0.70,
    "rgada-350-2-1621": 0.66,
    "rgada-350-2-1622": 0.49,
}
EPOCHS = [  # (с, по, доля верных знаков или None, знак, на чём мерено)
    (1500, 1660, None, "🟨",
     "скоропись 1620–1650-х мерена только на отложенных листах книги 1632 года, другие листы которой "
     "модель видела при обучении: 75 % верных знаков. Чужая рука этого времени читается хуже; "
     "насколько — не мерено"),
    (1661, 1700, 0.93, "🟩",
     "1680 год: 93 % верных знаков на 101 размеченной вручную строке"),
    (1701, 1735, 0.90, "🟩",
     "1718–1720-е: 90 % верных знаков на размеченных вручную строках четырёх книг, "
     "которых модель при обучении не видела"),
    (1736, 1800, 0.61, "🟨",
     "1740-е: 61 % верных знаков на размеченных вручную строках трёх книг 1748 года, "
     "которых модель при обучении не видела, — от 49 до 70 % в зависимости от писца"),
]


def accuracy(c):
    """(доля верных знаков или None, знак-потолок, на чём мерено) — либо None, если мерки нет."""
    if not c.get("htr") or not (c.get("htr_model") or "").startswith("скоропись-12"):
        return None
    if c["id"] in MEASURED:
        x = MEASURED[c["id"]]
        return (x, mark_of(x), f"{round(x * 100)} % верных знаков на размеченных вручную строках этого дела")
    y = c.get("year_from")
    if y is None:
        return None
    for lo, hi, x, m, basis in EPOCHS:
        if lo <= y <= hi:
            # Мерки эпох сняты со сплошного текста. Табличная книга — имя, отчество и возраст в разных
            # клетках — читается заметно хуже (болховские книги 1720-х: 9-19 % обрывков строк), и
            # сплошная мерка ей не потолок, а завышение.
            if c.get("tabular") and m == "🟩":
                return (None, "🟨", basis + ". Книга табличная, а мерка снята со сплошного текста: "
                        "табличные книги этого времени не мерены и читаются хуже")
            return (x, m, basis)
    return None


ORDER = ["🟥", "🟨", "🟩"]


def grade(c):
    s = score(c)
    if s is None:
        return None
    g = mark_of(s)
    a = accuracy(c)
    if a:
        g = min(g, a[1], key=ORDER.index)
    return g


# Описи, набранные волонтёрами: читаются без входа и без оплаты. Страница есть
# на каждый фонд (`/archive/<архив>/<фонд>/`), а на опись — нет: адрес с номером
# описи отдаёт 404. Поэтому ведём на фонд. Пермского края у них нет вовсе, и
# ссылки для ГАПК не будет — пустая ссылка хуже её отсутствия.
VELIKIE_SLUG = {"РГАДА": "rgada", "ГАСО": "gaso-ural"}


# У волонтёров набраны не все фонды: страницы ф.281 и ф.1642 отдают 404, и
# ссылка на них — обещание, которого никто не давал. Перечислены те, что
# проверены и отвечают.
VELIKIE_FONDS = {"РГАДА": {"214", "350", "1111", "1209", "1455"}}


def velikie(c):
    slug = VELIKIE_SLUG.get(c["arch"])
    if not slug or c["f"] not in VELIKIE_FONDS.get(c["arch"], set()):
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
    """Строка карточки: знак и числа. Как знак выставлен, объясняет README, а не каждая карточка."""
    mark = grade(c)
    if not mark:
        return None
    bits = [f"{c['htr'].replace('.', ',')} знака на строку"] if c.get("htr") else []
    if c.get("htr_conf"):
        bits.append(f"уверенность {c['htr_conf'].replace('.', ',')}")
    if c.get("tabular"):
        bits.append("дело табличное")
    return f"{mark} — " + ", ".join(bits)


def card(c):
    lines = [f"# {c['arch']} {cipher(c)}", ""]
    lines.append(f"**{c['title']}**")
    lines.append("")
    for i, u in enumerate(c["uezd"]):
        lines.append(f"{'Где: ' if i == 0 else '    '}{where_line(u, '../')}  ")
    lines.append("")
    lines.append(f"| | |")
    lines.append(f"|---|---|")
    lines.append(f"| Годы | {c['years'] or '—'} |")
    lines.append(f"| Что за книга | {book(c)} |")
    if c.get("estates"):
        lines.append(f"| Кто записан | {estates(c)} |")
    if c.get("places"):
        lines.append(f"| Места в деле | {places_cell(c, full=True)} |")
    for g in c.get("guides") or []:
        lines.append(f"| Путеводитель по листам | [{g.split('/')[-1][:-3]}](../{g}) |")
    lines.append(f"| Состояние | {STATE_MARK.get(c['state'], c['state'])} |")
    lines.append(f"| Образы | {c['scans'] or '—'} |")
    vol = volume(c)
    if vol:
        lines.append(f"| Объём | {vol} |")
    where = "ГИС УИАД" if "online.archives.ru" in (c.get("case_url") or "") else "каталог архива"
    if c.get("case_url"):
        lines.append(f"| Дело в каталоге | [{where}]({c['case_url']}) |")
    bits = []
    if c.get("opis"):
        bits.append(c["opis"])
    # В ГИС УИАД адрес описи получается из адреса дела отбрасыванием последнего
    # сегмента: каталог там иерархический, и опись, через которую к делу пришли,
    # по определению та, в которой оно лежит. У ГАПК адрес плоский —
    # `/archive1/unit/<id>` ничего не говорит об описи, — и её адрес берётся из
    # таблицы, а не выводится.
    uiad = OPIS_UIAD.get((c["arch"], c["f"], c["o"]))
    fond = FOND_UIAD.get((c["arch"], c["f"]))
    number = int(c["d"]) if c["d"].isdigit() else None
    if c.get("opis_url"):
        # Запись не об одном деле, а о группе: у ф.1455 это два десятка актов,
        # у ф.1642 — коллекция приказных изб. Отдельного адреса у такой записи
        # быть не может, и опись здесь — самый точный уровень, какой существует.
        bits.append(f"[ф.{c['f']} оп.{c['o']} в ГИС УИАД]({c['opis_url']})")
    elif c.get("case_url") and "online.archives.ru" in c["case_url"]:
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
    if bits:
        lines.append(f"| Опись | {' · '.join(bits)} |")
    if c.get("unit") and not c.get("case_url"):
        lines.append(f"| Дело в просмотрщике | [unit {c['unit']}]({GAPK}unit/{c['unit']}) |")
    if c.get("set"):
        url = f"[{c['set']}]({c['set_url']})" if c.get("set_url") else c["set"]
        lines.append(f"| Набор | {url} |")
    if c.get("htr"):
        here = (ROOT / "text" / f"{c['id']}.md").exists()
        where = f"[текст](../text/{c['id']}.md), " if here else ""
        lines.append(
            f"| Машинное чтение | {where}модель {model_link(c['htr_model'])} |"
        )
        v = verdict(c)
        if v:
            lines.append(f"| Чего стоит чтение | {v} |")
    lines.append("")
    for u in c["uezd"]:
        n = neighbours(c, u)
        if n:
            lines.append(n)
            lines.append("")
    if c.get("note"):
        lines.append(c["note"])
        lines.append("")
    if c.get("htr"):
        lines.append(
            "> Машинное чтение не является транскрипцией. Модель ошибается в знаках "
            "и способна дать связный, но неверный текст. Пригодно для поиска страницы по корню слова; для цитирования "
            "непригодно."
        )
        lines.append("")
    back = " · ".join(f"[{geo.REGIONS[r]}](../regions/{r}.md)" for r in regions_of(c))
    lines.append(f"← {back} · [указатель по шифрам](../CATALOG.md) · [о правах](../rights.md)")
    return "\n".join(lines) + "\n"


def state_cell(c):
    """Состояние одним словом; у распознанных — ещё знак качества, без чисел.

    Пробелы здесь неразрывные. Ячейка узкая, и на обычном пробеле браузер
    переносит знак качества на вторую строку — квадрат уезжает под слово и
    читается как отдельная запись.
    """
    cell = STATE_MARK.get(c["state"], c["state"]).replace(" ", "\u00a0")
    g = grade(c)
    return f"{cell}\u00a0{g}" if g else cell


ARCH_ORDER = {"РГАДА": 0, "СПб ИИ РАН": 1, "ГАПК": 2}
TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r",
                     "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"]))


def anchor(uezd):
    """ASCII-якорь уезда: кириллические id заголовков GitHub и kramdown строят по-разному."""
    return "u-" + "".join(TRANSLIT.get(ch, ch) for ch in uezd.lower())


def num(x):
    return int(x) if str(x).isdigit() else 10 ** 9


def cipher_key(c):
    return (ARCH_ORDER.get(c["arch"], 9), c["arch"], num(c["f"]), c["f"], num(c["o"]), num(c["d"]), c["d"])


def year_key(c):
    return (c.get("year_from") if c.get("year_from") is not None else 10 ** 4, c.get("year_to") or 0, cipher_key(c))


def is_collection(c):
    return c.get("kind") in geo.COLLECTION_KINDS and not str(c["d"]).isdigit()


def regions_of(c):
    out = []
    for u in c["uezd"]:
        for r in geo.region_of(u):
            if r not in out:
                out.append(r)
    return sorted(out, key=list(geo.REGIONS).index)


def where_line(u, up):
    regs = geo.region_of(u)
    links = " · ".join(f"[{geo.REGIONS[r]}]({up}regions/{r}.md#{anchor(u)})" for r in regs)
    return f"{links} → **{u} уезд** ({geo.UEZDS[u][1]})"


def book(c, uezd=None):
    """Одной строкой, что это за книга: «II ревизия, 1744–1748», «итоги переписи 1678–1679, без имён».

    У переписей название волны говорит всё, и вид книги к нему не приписывается. В Сибири
    перепись 1678 года шла в 1680–1683 годах, и в сибирском уезде подписывается так.
    """
    k, w = c["kind"], c.get("census")
    siberia = any(geo.UEZDS[u][2] for u in ([uezd] if uezd else c["uezd"]))
    if w:
        label = geo.CENSUS[w][1]
        if w == "1678":
            label = "перепись 1680–1683" if siberia else "перепись 1678–1679"
        if k == "итоги переписи":
            label = "итоги: " + label + ", без имён"
        elif k == "ландратская":
            label = "ландратская перепись 1715–1718"
        elif k not in ("ревизская", "писцовая", "переписная"):
            label = f"{geo.KINDS[k]} · {label}"
    else:
        label = geo.KINDS[k]
    if uezd and len(c["uezd"]) > 1:
        part = next((p for p in c.get("places") or [] if p["kind"] == "уезд" and p["name"] == uezd), None)
        if part and part.get("leaves"):
            label += f" · лл.{part['leaves']}"
    return label


def estates(c):
    return ", ".join("все сословия" if e == "все" else e for e in c.get("estates") or [])


def own_places(c, uezd=None):
    return [p for p in c.get("places") or []
            if p["kind"] != "уезд" and (uezd is None or p.get("uezd", c["uezd"][0]) == uezd)]


def places_cell(c, uezd=None, full=False, up=""):
    """В карточке — всё с листами; в таблице области — коротко, деревни числом."""
    ps = own_places(c, uezd)
    if full:
        return "; ".join(geo.place_label(p) + (f" — {p['leaves']}" if p.get("leaves") else "") for p in ps)
    big = [p for p in ps if p["kind"] not in ("деревня", "село")]
    small = len(ps) - len(big)
    names = [geo.place_label(p) for p in big]
    if len(names) > 5:
        names = names[:4] + [f"и ещё {len(names) - 4}"]
    if small:
        names.append(f"{small} {plural(small, 'деревня', 'деревни', 'деревень')}"
                     if small > 1 else geo.place_label(next(p for p in ps if p['kind'] in ('деревня', 'село'))))
    return ", ".join(names)


def plural(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def in_uezd(u):
    return sorted((c for c in CASES if u in c["uezd"] and not is_collection(c)), key=year_key)


def short(c):
    wave = f", {geo.CENSUS[c['census']][0]} ревизия" if (c.get("census") or "").startswith("rev") else ""
    return f"{c['years'] or '—'} {cipher(c)}{wave}"


def neighbours(c, u):
    if is_collection(c):
        return None
    row = in_uezd(u)
    i = row.index(c)
    prev = row[i - 1] if i > 0 else None
    nxt = row[i + 1] if i + 1 < len(row) else None
    if not prev and not nxt:
        return None
    bits = []
    if prev:
        bits.append(f"← раньше: [{short(prev)}]({prev['id']}.md)")
    if nxt:
        bits.append(f"позже: [{short(nxt)}]({nxt['id']}.md) →")
    return f"**{u} уезд по годам** — " + " · ".join(bits)


def coverage(u):
    """Какие общие переписи по уезду в справочнике есть, а каких между ними пока нет.

    Говорится именно «в справочнике нет», а не «не сохранилось»: отсутствие дела
    здесь значит только, что его сюда ещё не внесли.
    """
    have = {c["census"] for c in in_uezd(u) if c.get("census")}
    if not have:
        return None
    ranks = sorted(geo.census_rank(k) for k in have)
    keys = list(geo.CENSUS)
    siberia = geo.UEZDS[u][2]
    missing = [k for k in keys[ranks[0]:ranks[-1] + 1]
               if k not in have and not (siberia and k in geo.NOT_IN_SIBERIA)]
    line = "Общие переписи в справочнике: " + " · ".join(geo.CENSUS[k][0] for k in keys if k in have) + "."
    if missing:
        line += " Между ними пока не внесены: " + "; ".join(geo.CENSUS[k][1] for k in missing) + "."
    return line


def region_page(slug):
    name = geo.REGIONS[slug]
    uezds = [u for u, (regs, _, _) in geo.UEZDS.items() if slug in regs and any(u in c["uezd"] for c in CASES)]
    out = [f"# {name}", "",
           "Дела по уездам, которые сейчас лежат в границах области. Внутри уезда — по годам, "
           "так что видно, какая перепись шла раньше и какая позже.", "",
           "Уезды: " + " · ".join(f"[{u}](#{anchor(u)})" for u in uezds), ""]
    for u in uezds:
        out += [f'<a id="{anchor(u)}"></a>', "", f"## {u} уезд", "", f"*{geo.UEZDS[u][1]}*", ""]
        cov = coverage(u)
        if cov:
            out += [cov, ""]
        rows = in_uezd(u)
        if rows:
            out += ["| Годы | Книга | Кто записан | Места | Состояние | Дело |", "|---|---|---|---|---|---|"]
            for c in rows:
                out.append(f"| {c['years'] or '—'} | {book(c, u)} | {estates(c) or '—'} "
                           f"| {places_cell(c, u) or '—'} | {state_cell(c)} "
                           f"| [{c['arch']}&nbsp;{cipher(c).replace(' ', '&nbsp;')}](../cases/{c['id']}.md) |")
            out.append("")
        coll = [c for c in CASES if u in c["uezd"] and is_collection(c)]
        if coll:
            out += ["Фонды и коллекции: " + "; ".join(
                f"[{c['arch']} {cipher(c)}](../cases/{c['id']}.md) — {c['title']} ({c['years']})" for c in coll), ""]
    out += ["[Все области](../README.md#gde-iskat) · [указатель мест](../places.md) · "
            "[указатель по шифрам](../CATALOG.md) · [поиск по машинным чтениям](../search.html)"]
    return "\n".join(out) + "\n"


def place_key(name):
    return name.lower().replace("ё", "е")


def places_page():
    groups = {}
    for c in CASES:
        for p in own_places(c):
            u = p.get("uezd", c["uezd"][0])
            key = (place_key(p["name"]), p["kind"], u, p.get("within", ""))
            groups.setdefault(key, (p, u, []))[2].append((c, p.get("leaves", "")))
    out = ["# Указатель мест", "",
           "Волости, слободы, станы, города и деревни, названные в делах справочника, — с листами, "
           "где они известны. Названия приведены к одной форме: в самих книгах одна волость "
           "пишется по-разному (Покшеньгская, Покшенская, Пукшенская), а деревня часто носит "
           "двойное имя через «тож». Искать стоит и по соседним написаниям.", "",
           "Указатель не полон: в него внесено то, что названо в описи, на карточке дела или "
           "найдено при чтении. Места, которых здесь нет, могут стоять в деле — сплошной "
           "поиск по именам и селениям идёт по наборам и [машинным чтениям](search.html).", "",
           "| Место | Уезд | Годы | Дело | Листы |", "|---|---|---|---|---|"]
    for key in sorted(groups):
        p, u, hits = groups[key]
        label = geo.place_label(p) + (f" ({p['within']})" if p.get("within") else "")
        for i, (c, leaves) in enumerate(sorted(hits, key=lambda h: year_key(h[0]))):
            out.append(f"| {'**' + label + '**' if i == 0 else ''} | {u if i == 0 else ''} "
                       f"| {c['years'] or '—'} | [{c['arch']} {cipher(c)}](cases/{c['id']}.md) | {leaves} |")
    out += ["", "[По областям](README.md#gde-iskat) · [указатель по шифрам](CATALOG.md)"]
    return "\n".join(out) + "\n"


def catalog():
    rows = sorted((c for c in CASES if not is_collection(c)), key=cipher_key)
    out = ["# Указатель по шифрам", "",
           "Все дела справочника по порядку шифров. Искать по месту удобнее "
           "[по областям](README.md#gde-iskat) или по [указателю мест](places.md).", "",
           "| Шифр | Годы | Уезд | Состояние | Заголовок |",
           "|---|---|---|---|---|"]
    for c in rows:
        t = c["title"]
        t = t[:60] + "…" if len(t) > 61 else t
        out.append(
            f"| [{c['arch']} {cipher(c)}](cases/{c['id']}.md) | {c['years'] or '—'} "
            f"| {', '.join(c['uezd'])} | {state_cell(c)} | {t} |"
        )
    coll = sorted((c for c in CASES if is_collection(c)), key=cipher_key)
    if coll:
        out += ["", "## Фонды и коллекции", "",
                "Не отдельные дела, а фонды или группы дел: в них ищут акты и челобитные, а не переписи.", "",
                "| Шифр | Годы | Уезд | Состояние | Заголовок |", "|---|---|---|---|---|"]
        for c in coll:
            out.append(f"| [{c['arch']} {cipher(c)}](cases/{c['id']}.md) | {c['years'] or '—'} "
                       f"| {', '.join(c['uezd'])} | {state_cell(c)} | {c['title']} |")
    out += ["",
            "Ресурсы, откуда всё это берётся, — в [sources.md](sources.md); "
            "что здесь можно публиковать и почему — в [rights.md](rights.md)."]
    return "\n".join(out) + "\n"


def regions_list():
    """Строки для README: область → уезды → сколько дел."""
    lines = []
    for slug, name in geo.REGIONS.items():
        uezds = [u for u, (regs, _, _) in geo.UEZDS.items() if slug in regs]
        parts = []
        for u in uezds:
            n = sum(1 for c in CASES if u in c["uezd"])
            if n:
                parts.append(f"[{u}](regions/{slug}.md#{anchor(u)}) — {n} {plural(n, 'дело', 'дела', 'дел')}")
        if parts:
            lines.append(f"- **[{name}](regions/{slug}.md)**: " + ", ".join(parts))
    return lines


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


def public(c):
    """Запись каталога для программ: то же, что в карточке, без служебных полей."""
    here = (ROOT / "text" / f"{c['id']}.md").exists()
    return {
        "id": c["id"], "archive": c["arch"], "fond": c["f"], "inventory": c["o"], "unit": c["d"],
        "title": c["title"], "years": c.get("years") or None, "state": c["state"],
        "scans": c.get("scans") or None, "leaves": c.get("leaves"), "images": c.get("images"),
        "case_url": c.get("case_url") or None,
        "transcription": ({"title": c["set"], "url": c.get("set_url") or None} if c.get("set") else None),
        "machine_reading": ({
            "model": c["htr_model"], "model_url": model_url(c["htr_model"]),
            "chars_per_line": float(c["htr"]), "mean_confidence": float(c["htr_conf"]) if c.get("htr_conf") else None,
            "tabular": bool(c.get("tabular")), "grade": grade(c) or None,
            "score": round(score(c), 2) if grade(c) else None,
            "accuracy": ({"char_accuracy": accuracy(c)[0], "basis": accuracy(c)[2]} if accuracy(c) else None),
            "text": f"text/{c['id']}.md" if here else None,
            "data": f"data/readings/{c['id']}.json" if here else None,
        } if c.get("htr") else None),
        "card": f"cases/{c['id']}.md",
        "regions": [geo.REGIONS[r] for r in regions_of(c)],
        "uezd": c["uezd"],
        "year_from": c.get("year_from"), "year_to": c.get("year_to"),
        "kind": c["kind"],
        "census": ({"key": c["census"], "title": geo.CENSUS[c["census"]][1]} if c.get("census") else None),
        "estates": c.get("estates") or [],
        "places": [{k: p[k] for k in ("name", "kind", "uezd", "within", "leaves") if p.get(k)}
                   | ({"uezd": c["uezd"][0]} if "uezd" not in p and p["kind"] != "уезд" else {})
                   for p in c.get("places") or []],
        "guides": c.get("guides") or [],
        "note": c.get("note") or None,
    }


def readme():
    """Список областей в README собирается, остальной README пишется руками."""
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    a, b = "<!-- regions -->", "<!-- /regions -->"
    if a not in text:
        return
    head, rest = text.split(a, 1)
    tail = rest.split(b, 1)[1]
    path.write_text(head + a + "\n" + "\n".join(regions_list()) + "\n" + b + tail, encoding="utf-8")


def main():
    bad = [f"{c['id']}: {e}" for c in CASES for e in geo.validate(c)]
    if bad:
        raise SystemExit("cases.json не сходится со словарями tools/geo.py:\n  " + "\n  ".join(bad))
    (ROOT / "cases").mkdir(exist_ok=True)
    (ROOT / "regions").mkdir(exist_ok=True)
    (ROOT / "data").mkdir(exist_ok=True)
    pub = [public(c) for c in CASES]
    (ROOT / "data" / "cases.json").write_text(json.dumps(
        {"schema_version": 1, "cases": pub}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    warn = [w for w in (check(c) for c in CASES) if w]
    for c in CASES:
        (ROOT / "cases" / f"{c['id']}.md").write_text(card(c), encoding="utf-8")
    (ROOT / "CATALOG.md").write_text(catalog(), encoding="utf-8")
    slugs = sorted({r for c in CASES for r in regions_of(c)}, key=list(geo.REGIONS).index)
    for old in (ROOT / "regions").glob("*.md"):
        if old.stem not in slugs:
            old.unlink()
    for r in slugs:
        (ROOT / "regions" / f"{r}.md").write_text(region_page(r), encoding="utf-8")
    (ROOT / "places.md").write_text(places_page(), encoding="utf-8")
    readme()
    n, shards, words, postings, size = search_index.build(pub)
    print(f"поиск: дел {n}, словоформ {words}, {size / 1e6:.1f} МБ в {shards} файлах")
    print(f"карточек {len(CASES)}, областей {len(slugs)}, каталог собран")
    for w in warn:
        print("  ПРОВЕРЬТЕ:", w)


if __name__ == "__main__":
    main()
