"""Модели, которыми сделаны машинные чтения: название в cases.json → ссылка на опубликованные веса.

Версия указывается та, которой дело действительно читалось: у каждой версии «скорописи-12»
свой DOI на Zenodo, и чтение воспроизводится только ею.
"""

MODELS = {
    "скоропись-12": "https://doi.org/10.5281/zenodo.22905381",
    "скоропись-12 v3": "https://doi.org/10.5281/zenodo.22912945",
    "скоропись-12 v8": "https://doi.org/10.5281/zenodo.22933888",
    "Kansallisarkisto/cyrillic-htr-model": "https://huggingface.co/Kansallisarkisto/cyrillic-htr-model",
}


def model_link(name):
    url = MODELS.get(name)
    return f"[{name}]({url})" if url else f"«{name}»"
