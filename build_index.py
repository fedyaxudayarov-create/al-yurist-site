# build_index.py
import os
import re
import json
import hashlib
from pathlib import Path
from collections import defaultdict, Counter

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUT_PATH = DATA_DIR / "search_index.json"

# -----------------------------
# Text helpers
# -----------------------------
def read_text_best_effort(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "cp1251", "windows-1251", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    # fallback
    return raw.decode("utf-8", errors="ignore")

def normalize_space(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

# Uzbek apostrophe normalization
def norm_apostrophes(s: str) -> str:
    return (
        s.replace("’", "'")
         .replace("ʻ", "'")
         .replace("ʼ", "'")
         .replace("`", "'")
    )

# Minimal translit: Cyrillic -> Latin (approx) and Latin -> Cyrillic (approx)
_C2L = {
    "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"yo","ж":"j","з":"z","и":"i","й":"y","к":"k","л":"l","м":"m",
    "н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f","х":"x","ц":"ts","ч":"ch","ш":"sh","щ":"sh",
    "ъ":"","ь":"","э":"e","ю":"yu","я":"ya","қ":"q","ғ":"g'","ҳ":"h","ў":"o'",
}
def cyr_to_lat(s: str) -> str:
    out = []
    for ch in s:
        low = ch.lower()
        if low in _C2L:
            rep = _C2L[low]
            out.append(rep)
        else:
            out.append(ch.lower())
    return "".join(out)

# very rough latin->cyr (only for matching)
_L2C_MULTI = [
    ("g'", "ғ"), ("o'", "ў"),
    ("sh", "ш"), ("ch", "ч"), ("yo", "ё"), ("yu", "ю"), ("ya", "я"), ("ts", "ц"),
]
_L2C_SINGLE = {
    "a":"а","b":"б","v":"в","g":"г","d":"д","e":"е","j":"ж","z":"з","i":"и","y":"й","k":"к","l":"л","m":"м",
    "n":"н","o":"о","p":"п","r":"р","s":"с","t":"т","u":"у","f":"ф","x":"х","h":"ҳ","q":"қ",
}
def lat_to_cyr(s: str) -> str:
    s = s.lower()
    for a, b in _L2C_MULTI:
        s = s.replace(a, b)
    out = []
    for ch in s:
        out.append(_L2C_SINGLE.get(ch, ch))
    return "".join(out)

TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁёҚқҒғҲҳЎў']{2,}")

def tokenize(text: str):
    text = norm_apostrophes(text.lower())
    return TOKEN_RE.findall(text)

# -----------------------------
# Splitting into articles (modda)
# -----------------------------
# Supports:
# "1-модда", "1 - модда", "Модда 1", "1-modda", "Modda 1"
MODDA_HEADER_RE = re.compile(
    r"(?im)^(?:\s*)("
    r"(?:\d+\s*[-–—]?\s*(?:модда|modda))"
    r"|(?:модда|modda)\s*\d+"
    r")\b[^\n]*$"
)

def extract_modda_no(header_line: str) -> str:
    header_line = header_line.lower()
    m = re.search(r"(\d+)", header_line)
    return m.group(1) if m else ""

def split_into_chunks(full_text: str):
    """
    Returns list of (modda_no, title, chunk_text)
    If no modda headers found -> one chunk with modda_no="".
    """
    full_text = normalize_space(full_text)
    lines = full_text.split("\n")
    # find header line indices
    header_idx = []
    for i, line in enumerate(lines):
        if MODDA_HEADER_RE.match(line.strip()):
            header_idx.append(i)

    if not header_idx:
        # no explicit modda -> fallback as one chunk
        title = lines[0].strip()[:120] if lines else ""
        return [("", title, full_text)]

    chunks = []
    for pos, idx in enumerate(header_idx):
        start = idx
        end = header_idx[pos + 1] if pos + 1 < len(header_idx) else len(lines)
        header = lines[idx].strip()
        modda_no = extract_modda_no(header)
        body_lines = lines[start:end]
        chunk_text = "\n".join(body_lines).strip()
        title = header
        chunks.append((modda_no, title, chunk_text))
    return chunks

def doc_id(source: str, modda_no: str, text: str) -> str:
    h = hashlib.sha1()
    h.update((source + "|" + modda_no + "|" + text[:2000]).encode("utf-8", errors="ignore"))
    return h.hexdigest()[:16]

# -----------------------------
# Build index
# -----------------------------
def main():
    if not DATA_DIR.exists():
        raise SystemExit(f"ERROR: data/ folder not found: {DATA_DIR}")

    txt_files = sorted([p for p in DATA_DIR.glob("*.txt") if p.is_file()])
    if not txt_files:
        raise SystemExit("ERROR: data/ папкада .txt файл йўқ. (масалан: mehnat_kodeksi.txt)")

    docs = []
    inverted = defaultdict(list)   # token -> [doc_index]
    sources = []

    for path in txt_files:
        source_key = path.stem  # e.g. mehnat_kodeksi
        sources.append(source_key)

        text = read_text_best_effort(path)
        text = norm_apostrophes(text)
        text = normalize_space(text)

        chunks = split_into_chunks(text)

        for modda_no, title, chunk_text in chunks:
            did = doc_id(source_key, modda_no, chunk_text)
            docs.append({
                "id": did,
                "source": source_key,
                "modda": modda_no,
                "title": title[:200],
                "text": chunk_text,
            })

    # Build inverted index with extra translit tokens
    for idx, d in enumerate(docs):
        toks = tokenize(d["text"])
        # add translit variants for matching
        extra = []
        for t in toks:
            extra.append(cyr_to_lat(t))
            extra.append(lat_to_cyr(t))
        all_toks = toks + extra

        counts = Counter([t for t in all_toks if len(t) >= 2])
        for t, c in counts.items():
            inverted[t].append([idx, c])  # doc idx + term freq

    out = {
        "version": 1,
        "sources": sorted(set(sources)),
        "docs": docs,
        "inverted": dict(inverted),
        "meta": {
            "files": len(txt_files),
            "docs": len(docs),
            "tokens": len(out := inverted),  # just for quick stats
        }
    }
    # fix meta.tokens (since we used out variable trick above)
    out["meta"]["tokens"] = len(out["inverted"])

    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"OK: built index -> {OUT_PATH}")
    print(f"Stats: files={len(txt_files)} docs={len(docs)} tokens={len(out['inverted'])}")
    print("Tip: endi app.py шу data/search_index.json дан қидириши керак.")

if __name__ == "__main__":
    main()
