# build_index.py
# data/ папкадаги .txt қонунларни "модда"ларга бўлиб, data/search_index.json қилиб индекс тайёрлайди.

import json
import re
from pathlib import Path
from collections import defaultdict, Counter

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUT_PATH = DATA_DIR / "search_index.json"

# --- Transliteration (very small + practical) ---
_LAT2CYR = str.maketrans({
    "a": "а", "b": "б", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "ҳ", "i": "и", "j": "ж",
    "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "q": "қ", "r": "р",
    "s": "с", "t": "т", "u": "у", "v": "в", "x": "х", "y": "й", "z": "з",
})
_CYR2LAT = str.maketrans({
    "а": "a", "б": "b", "д": "d", "е": "e", "ф": "f", "г": "g", "ҳ": "h", "и": "i", "ж": "j",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "қ": "q", "р": "r",
    "с": "s", "т": "t", "у": "u", "в": "v", "х": "x", "й": "y", "з": "z",
    "ў": "o", "ғ": "g", "ш": "sh", "ч": "ch",
})

def lat_to_cyr(s: str) -> str:
    return s.lower().translate(_LAT2CYR)

def cyr_to_lat(s: str) -> str:
    return s.lower().translate(_CYR2LAT)

def normalize_spaces(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def tokenize(text: str) -> list[str]:
    # harf/raqamlarni оламиз
    text = text.lower()
    parts = re.findall(r"[a-zа-яёғўқҳчш0-9]+", text, flags=re.IGNORECASE)
    return [p for p in parts if p]

def guess_source_key(filename: str) -> str:
    name = filename.lower().replace(".txt", "")
    return name

# Модда сарлавҳасини ушлаб олади:
# "14-модда", "14 - модда", "Модда 14", "14-модда." ва кирилл/лотин аралаш вариантлар
MODDA_RE = re.compile(
    r"(?im)^(?:\s*(\d{1,4})\s*[-–—]?\s*модда\b|\s*модда\s*(\d{1,4})\b)\.?\s*(.*)$"
)

def split_into_modda_chunks(text: str):
    """
    return list of tuples: (modda_no(str), title(str), chunk_text(str))
    """
    lines = text.splitlines()
    hits = []
    for i, ln in enumerate(lines):
        m = MODDA_RE.match(ln.strip())
        if m:
            no = m.group(1) or m.group(2)
            title = (m.group(3) or "").strip()
            hits.append((i, no.strip(), title))

    if not hits:
        return []

    chunks = []
    for idx, (line_i, no, title) in enumerate(hits):
        start = line_i
        end = hits[idx + 1][0] if idx + 1 < len(hits) else len(lines)
        block = "\n".join(lines[start:end]).strip()
        block = normalize_spaces(block)
        if len(block) < 50:
            continue
        chunks.append((no, title, block))
    return chunks

def fallback_chunks(text: str, max_chars=2200):
    # модда топилмаса, параграфларга бўлиб чиқамиз
    text = normalize_spaces(text)
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    out = []
    buf = []
    size = 0
    for p in paras:
        if size + len(p) > max_chars and buf:
            out.append("\n\n".join(buf))
            buf, size = [], 0
        buf.append(p)
        size += len(p)
    if buf:
        out.append("\n\n".join(buf))
    return out

def doc_id(source: str, modda: str, text: str) -> str:
    # deterministic id
    base = f"{source}|{modda}|{hash(text)}"
    return str(abs(hash(base)))

def main():
    if not DATA_DIR.exists():
        raise SystemExit(f"data folder topilmadi: {DATA_DIR}")

    txt_files = sorted(DATA_DIR.glob("*.txt"))
    if not txt_files:
        raise SystemExit("data/ ичида .txt файл йўқ. (масалан: mehnat_kodeksi.txt)")

    docs = []
    sources = []
    inverted = defaultdict(list)

    for p in txt_files:
        source_key = guess_source_key(p.name)
        sources.append(source_key)
        raw = p.read_text(encoding="utf-8", errors="ignore")
        raw = normalize_spaces(raw)

        modda_chunks = split_into_modda_chunks(raw)
        if modda_chunks:
            for modda_no, title, chunk_text in modda_chunks:
                did = doc_id(source_key, modda_no, chunk_text)
                docs.append({
                    "id": did,
                    "source": source_key,
                    "modda": modda_no,
                    "title": title[:200],
                    "text": chunk_text,
                })
        else:
            # fallback
            parts = fallback_chunks(raw)
            for i, chunk_text in enumerate(parts, start=1):
                did = doc_id(source_key, str(i), chunk_text)
                docs.append({
                    "id": did,
                    "source": source_key,
                    "modda": str(i),
                    "title": "",
                    "text": chunk_text,
                })

    # Build inverted index (token -> [[doc_index, tf], ...])
    for doc_idx, d in enumerate(docs):
        toks = tokenize(d["text"])

        # кирилл-лотин вариантларни ҳам қўшамиз (қидирув осон бўлади)
        extra = []
        for t in toks:
            extra.append(cyr_to_lat(t))
            extra.append(lat_to_cyr(t))

        all_toks = toks + extra
        counts = Counter([t for t in all_toks if len(t) >= 2])

        for t, c in counts.items():
            inverted[t].append([doc_idx, c])

    out = {
        "version": 2,
        "sources": sorted(set(sources)),
        "docs": docs,
        "inverted": dict(inverted),
        "meta": {
            "files": len(txt_files),
            "docs": len(docs),
            "tokens": len(inverted),
        }
    }

    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"OK: built index -> {OUT_PATH}")
    print(f"Stats: files={len(txt_files)} docs={len(docs)} tokens={len(inverted)}")

if __name__ == "__main__":
    main()
