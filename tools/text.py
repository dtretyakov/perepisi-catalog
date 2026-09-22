#!/usr/bin/env python3
"""Выложить машинные чтения в text/<дело>.md.

Читает из рабочего каталога исследования (не входит в репозиторий) и пишет
markdown — по файлу на дело, по заголовку на лист. Образы не копируются
никогда: п. 6.3 соглашения ГИС УИАД, см. rights.md.
"""
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = Path(os.environ.get("GENEA_CORPUS", Path.home() / ".genea" / "corpus"))
CASES = json.loads((ROOT / "tools" / "cases.json").read_text(encoding="utf-8"))

# Одно дело может лежать в нескольких папках корпуса: д.1340 снималось двумя
# заходами, и нумерация у них разная — начало дела шло по образам, Веркольская
# волость по листам. Мешать их в один ряд нельзя, поэтому части идут подряд.
EXTRA = {
    "rgada-350-2-1340": [
        ("rgada-350-2-1340-alf", "Начало дела, нумерация по образам"),
        ("rgada-350-2-1340-lav", "Веркольская волость, нумерация по листам"),
    ]
}

LEAF = re.compile(r"^l0*(\d+)(об|[ab])?", re.IGNORECASE)


def leaf_key(page):
    m = LEAF.match(page)
    if not m:
        return (10**9, 0, page)
    side = {"об": 1, "a": 0, "b": 1, None: 0}[m.group(2).lower() if m.group(2) else None]
    return (int(m.group(1)), side, page)


def leaf_name(page):
    """«л. 103об» или «образъ 4b» — как дело было снято, так и подписано."""
    m = LEAF.match(page)
    if not m:
        return page
    n, suf = m.group(1), (m.group(2) or "")
    if suf.lower() in ("a", "b"):
        return f"образ {int(n)}{suf.lower()}"
    return f"л. {int(n)}{suf}"


def parts(case_id):
    """[(подпись части или None, листы)] — части в том порядке, что и дело."""
    out = []
    for d, caption in EXTRA.get(case_id, [(case_id, None)]):
        f = CORPUS / d / "read.jsonl"
        if not f.exists():
            continue
        ps = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        ps.sort(key=lambda p: leaf_key(p["page"]))
        if ps:
            out.append((caption, ps))
    return out


def render(c, prts):
    ciph = f"ф.{c['f']} оп.{c['o']} д.{c['d']}"
    ps = [p for _, part in prts for p in part]
    n = sum(len(p["lines"]) for p in ps)
    out = [
        f"# {c['arch']} {ciph} — машинное чтение",
        "",
        f"**{c['title']}**",
        "",
        f"Годы: {c['years'] or '—'}. Листов прочитано: {len(ps)}, строк: {n}. "
        f"Модель «{c['htr_model']}», {c['htr']} знака на строку"
        + (f", средняя уверенность {c['htr_conf']}." if c.get("htr_conf") else "."),
        "",]
    # Оговорка про таблицу — свойство ДЕЛА, а не того, что у нас посчитана
    # уверенность. Ревизская сказка 1811 года разбита на клетки и даёт 8-10
    # знаков на строку при отличном чтении; сказки 1719 года идут сплошным
    # текстом и дают тридцать три. Вешать на них один и тот же дисклеймер
    # значит учить читателя не верить верному числу.
    if c.get("tabular"):
        out += [
        "> Дело табличное: имя, отчество, фамилия и возраст расположены в разных "
        "клетках, и число знаков на строку здесь непоказательно. Следует "
        "ориентироваться на среднюю уверенность.",
        "",]
    out += [
        "> **Это машинное распознавание, а не транскрипция.** Модель ошибается в "
        "знаках, смешивает близкие буквы и способна дать связный, но неверный "
        "текст. Материал пригоден для **поиска листа** по корню слова; для "
        "цитирования непригоден. Найденное место следует сверять с образом.",
        "",
        "Порядок поиска: по корню с заменой гласных — модель передаёт «Тренка» как "
        "«Тронка», «пенежан» как «пинежени». Просматривать следует все "
        "совпадения, а не первое.",
        "",
        f"Шифр для ссылки: **{c['arch']} {ciph}**. В заголовке куска стоит то, "
        "чем дело снято: «л. N» — лист, «образ Na/Nb» — левая и правая "
        "страницы одного разворота. Перевести образ в лист может только "
        "оглавление дела, и здесь этого не делается.",
        "",
        f"[← карточка дела](../cases/{c['id']}.md) · [о правах](../rights.md)",
        "",
        "---",
        "",
    ]
    for caption, part in prts:
        if caption:
            out += [f"**{caption}**", ""]
        for p in part:
            lines = [l.strip() for l in p["lines"] if l.strip()]
            if not lines:
                continue
            out.append(f"## {leaf_name(p['page'])}")
            out.append("")
            out += lines
            out.append("")
    return "\n".join(out) + "\n"


def main():
    (ROOT / "text").mkdir(exist_ok=True)
    made = []
    for c in CASES:
        if not c.get("htr"):
            continue
        prts = parts(c["id"])
        if not prts:
            print(f"  нет чтения: {c['id']}")
            continue
        (ROOT / "text" / f"{c['id']}.md").write_text(render(c, prts), encoding="utf-8")
        made.append((c["id"], sum(len(p) for _, p in prts)))
    for i, n in made:
        print(f"  {i}: листов {n}")
    print(f"дел с чтением {len(made)}")


if __name__ == "__main__":
    main()
