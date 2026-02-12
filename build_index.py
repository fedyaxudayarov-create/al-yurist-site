# build_index.py
# -*- coding: utf-8 -*-

import os
import re
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUT_PATH = os.path.join(DATA_DIR, "index.json")

# Қайси файл қайси категория экани
SOURCES = [
    ("mehnat", "Меҳнат кодекси", "mehnat_kodeksi.txt"),
    ("mamuriy", "Маъмурий жавобгарлик кодекси", "mamuriy_kodeks.txt"),
    ("jinoyat", "Жиноят кодекси", "jinoyat_kodeksi.txt"),
    ("konstitutsiya", "Конституция", "konstitutsiya.txt"),
    ("davlat_xizmati", "Давлат фуқаролик хизмати тўғрисидаги қонун", "davlat_xizmati.txt"),
    ("mahalliy_hokimiyat", "Маҳаллий давлат ҳокимияти тўғрисидаги қонун", "mahalliy_hokimiyat.txt"),
]

# "Модда 12." / "Modda 12." / "12-модда" каби вариантларни ушлаймиз
RE_ARTICLE_HEAD = re.compile(
    r"(?im)^\s*(?:"
    r"(?:МОДДА|Модда|Modda)\s*(\d+)\s*[\.\-:]?\s*(.*)$"
    r"|"
    r"(\d+)\s*[-–]\s*(?:модда|Модда|МОДДА)\s*[\.\-:]?\s*(.*)$"
    r")"
)

def read_text(path: str) -> str:
    # UTF-8, баъзи Word->txtларда BOM бўлиши мумкин
    with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
        return f.read()

def normalize_spaces(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # ортиқча пробел/қаторлар
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def split_by_articles(text: str):
    """
    Моддалар бўйича бўлиб беради.
    Агар модда топилмаса, None қайтаради.
    """
    matches = list(RE_ARTICLE_HEAD.finditer(text))
    if not matches:
        return None

    parts = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        # Гуруҳлар: (1)moddaNo (2)title ёки (3)moddaNo2 (4)title2
        modda_no = m.group(1) or m.group(3) or ""
        title = (m.group(2) or m.group(4) or "").strip()
        chunk = text[start:end].strip()

        parts.append((modda_no, title, chunk))
    return parts

def chunk_fallback(text: str, max_chars: int = 1800):
    """
    Агар модда бўлинмаса — катта матнни қисмларга бўлиб қўямиз
    """
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 2 <= max_chars:
            buf = (buf + "\n\n" + p).strip()
        else:
            if buf:
                chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks

def build_index():
    if not os.path.isdir(DATA_DIR):
        raise RuntimeError(f"data папка топилмади: {DATA_DIR}")

    items = []
    missing = []

    for cat, cat_title, filename in SOURCES:
        fpath = os.path.join(DATA_DIR, filename)
        if not os.path.isfile(fpath):
            missing.append(filename)
            continue

        raw = normalize_spaces(read_text(fpath))

        # 1) модда бўйича бўлиш
        parts = split_by_articles(raw)

        if parts:
            for idx, (modda_no, title, body) in enumerate(parts, start=1):
                # Жуда қисқа “модда”лар бўлса ташлаб кетамиз
                if len(body) < 40:
                    continue
                items.append({
                    "id": f"{cat}:{modda_no or idx}",
                    "cat": cat,
                    "cat_title": cat_title,
                    "label": f"Модда {modda_no}" if modda_no else f"Қисм {idx}",
                    "title": title,
                    "text": body,
                    "source_file": filename,
                })
        else:
            # 2) fallback chunk
            chunks = chunk_fallback(raw)
            for idx, ch in enumerate(chunks, start=1):
                if len(ch) < 80:
                    continue
                items.append({
                    "id": f"{cat}:chunk{idx}",
                    "cat": cat,
                    "cat_title": cat_title,
                    "label": f"Қисм {idx}",
                    "title": "",
                    "text": ch,
                    "source_file": filename,
                })

    meta = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_items": len(items),
        "missing_files": missing,
    }

    out = {
        "meta": meta,
        "items": items,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("[OK] index.json yozildi:", OUT_PATH)
    print("[OK] Jami items:", len(items))
    if missing:
        print("[WARN] Topilmagan fayllar:", ", ".join(missing))
    else:
        print("[OK] Hamma fayl bor.")

if __name__ == "__main__":
    build_index()
