#!/usr/bin/env python3
"""Собрать поисковый индекс по машинным чтениям: search/meta.json и search/idx/*.json.

Искать в машинном чтении дословно бесполезно: модель пишет «Тронка» вместо «Тренка» и
«пинежени» вместо «пенежан». Путает она прежде всего гласные, согласные держит заметно
твёрже. Поэтому слово индексируется по СКЕЛЕТУ: гласные схлопнуты в одну звёздочку,
ъ и ь выброшены, удвоенные согласные сведены к одной. «Булаев» → «б*л*в», и под этот
скелет попадают «Булаевъ», «Болаев» и «Булаив». Какая из найденных форм ближе к
запросу, решает уже страница — по расстоянию между словами.

Модель к тому же склеивает слово с предыдущим коротким: «Сенъбулаев» — это «сын Булаев».
Поэтому слово, которое начинается с «сын», «до», «на» и подобных, индексируется ещё и без
них, если остаток не короче пяти букв. Ложные остатки («помещик» → «мещик») безвредны:
их никто не ищет.

Индекс разложен по первым двум знакам скелета: страница поиска тянет один маленький
файл, а не всё сразу. Функции fold и skeleton повторены в search.html знак в знак;
поменяв одну, поменяйте и другую.
"""
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READINGS = ROOT / "data" / "readings"
OUT = ROOT / "search"

VOWELS = set("аеиоуыэюяй")
GLUE = ("сын", "сен", "син", "сн", "до", "на", "по", "за", "от", "из", "же", "да")
WORD = re.compile(r"[а-яёѣіїѳѵ]+")


def fold(w):
    w = w.lower()
    for a, b in (("ё", "е"), ("ѣ", "е"), ("і", "и"), ("ї", "и"), ("ѳ", "ф"), ("ѵ", "и")):
        w = w.replace(a, b)
    return w.replace("ъ", "").replace("ь", "")


def skeleton(w):
    out = []
    for ch in fold(w):
        k = "*" if ch in VOWELS else ch
        if out and out[-1] == k:
            continue
        out.append(k)
    return "".join(out)


def shard(sk):
    """Имя файла по первым двум знакам скелета — латиницей, чтобы адрес не зависел от кодировки."""
    return "_".join(f"{ord(ch):x}" for ch in sk[:2])


def build(cases_public):
    """cases_public — записи data/cases.json: из них берутся заголовки, уезды и оценки."""
    by_id = {c["id"]: c for c in cases_public}
    meta, index = [], defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    for path in sorted(READINGS.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        cid = d["case"]["id"]
        c = by_id.get(cid, {})
        ci = len(meta)
        labels = []
        for part in d["parts"]:
            for page in part["pages"]:
                pi = len(labels)
                labels.append(page["label"])
                for line in page["lines"]:
                    for w in WORD.findall(line.lower()):
                        f = fold(w)
                        if len(f) < 3:
                            continue
                        for form in [f] + [f[len(g):] for g in GLUE if f.startswith(g) and len(f) - len(g) >= 5]:
                            sk = skeleton(form)
                            if len(sk) >= 2:
                                index[shard(sk)][form][ci].add(pi)
        mr = c.get("machine_reading") or {}
        meta.append({
            "id": cid,
            "cipher": f"{d['case']['archive']} ф.{d['case']['fond']} оп.{d['case']['inventory']} д.{d['case']['unit']}",
            "title": d["case"]["title"],
            "years": d["case"].get("years"),
            "year_from": c.get("year_from"),
            "uezd": c.get("uezd") or [],
            "regions": c.get("regions") or [],
            "grade": mr.get("grade"),
            "labels": labels,
        })
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "idx").mkdir(parents=True)
    (OUT / "meta.json").write_text(json.dumps({"schema_version": 1, "cases": meta}, ensure_ascii=False,
                                              separators=(",", ":")), encoding="utf-8")
    words = postings = 0
    for key, ws in index.items():
        body = {w: {str(ci): sorted(ps) for ci, ps in hits.items()} for w, hits in sorted(ws.items())}
        words += len(body)
        postings += sum(len(ps) for hits in body.values() for ps in hits.values())
        (OUT / "idx" / f"{key}.json").write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")),
                                                  encoding="utf-8")
    size = sum(p.stat().st_size for p in OUT.rglob("*.json"))
    return len(meta), len(index), words, postings, size


if __name__ == "__main__":
    pub = json.loads((ROOT / "data" / "cases.json").read_text(encoding="utf-8"))["cases"]
    n, shards, words, postings, size = build(pub)
    print(f"поиск: дел {n}, файлов {shards}, словоформ {words}, вхождений {postings}, {size / 1e6:.1f} МБ")
