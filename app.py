# app.py
import json
import math
import re
from pathlib import Path
from collections import defaultdict

from flask import Flask, render_template, request, jsonify

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INDEX_PATH = DATA_DIR / "search_index.json"

app = Flask(__name__)

# --- translit helpers (same as build_index) ---
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

def tokenize(text: str) -> list[str]:
    text = (text or "").lower()
    parts = re.findall(r"[a-zа-яёғўқҳчш0-9]+", text, flags=re.IGNORECASE)
    return [p for p in parts if p]

# --- load index ---
INDEX = None
DOCS = None
INVERTED = None
IDF = None

SOURCE_LABELS = {
    "mehnat_kodeksi": "Меҳнат кодекси",
    "mamuriy_kodeks": "Маъмурий жавобгарлик (МЖтК)",
    "jinoyat_kodeksi": "Жиноят кодекси",
    "konstitutsiya": "Конституция",
    "davlat_xizmati": "Давлат фуқаролик хизмати",
    "fuqarolik_kodeksi": "Фуқаролик кодекси",
    "mahalliy_hokimiyat": "Маҳаллий давлат ҳокимияти тўғрисида",
}

def load_index():
    global INDEX, DOCS, INVERTED, IDF
    if not INDEX_PATH.exists():
        INDEX = {"docs": [], "inverted": {}, "meta": {}}
        DOCS, INVERTED, IDF = [], {}, {}
        return

    INDEX = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    DOCS = INDEX.get("docs", [])
    INVERTED = INDEX.get("inverted", {})

    # compute idf
    N = max(1, len(DOCS))
    df = {}
    for tok, postings in INVERTED.items():
        df[tok] = len(postings)
    IDF = {t: math.log((N + 1) / (dfv + 1)) + 1.0 for t, dfv in df.items()}

load_index()

def score_query(query: str, source_filter: str | None = None, limit: int = 20):
    if not query or not query.strip():
        return []

    q = query.strip()
    qtoks = tokenize(q)

    # add translit variants (query side)
    extra = []
    for t in qtoks:
        extra.append(cyr_to_lat(t))
        extra.append(lat_to_cyr(t))
    qtoks = qtoks + extra

    # detect "modda" number
    modda_num = None
    m = re.search(r"(\d{1,4})", q)
    if m:
        modda_num = m.group(1)

    scores = defaultdict(float)
    matched = set()

    for t in qtoks:
        postings = INVERTED.get(t)
        if not postings:
            continue
        idf = IDF.get(t, 1.0)
        for doc_idx, tf in postings:
            d = DOCS[doc_idx]
            if source_filter and d.get("source") != source_filter:
                continue
            scores[doc_idx] += (1.0 + math.log(1 + tf)) * idf
            matched.add(doc_idx)

    # boost exact modda match
    if modda_num:
        for doc_idx in list(matched):
            d = DOCS[doc_idx]
            if str(d.get("modda", "")).strip() == modda_num:
                scores[doc_idx] += 5.0

    ranked = sorted(matched, key=lambda i: scores[i], reverse=True)[:limit]

    results = []
    for i in ranked:
        d = DOCS[i]
        text = d.get("text", "")
        snippet = text[:420].replace("\n", " ")
        results.append({
            "source": d.get("source"),
            "source_label": SOURCE_LABELS.get(d.get("source"), d.get("source")),
            "modda": d.get("modda"),
            "title": d.get("title", ""),
            "snippet": snippet + ("..." if len(text) > 420 else ""),
            "score": round(scores[i], 4),
        })
    return results

@app.route("/", methods=["GET"])
def home():
    # UI сизда templates/index.html да турибди
    return render_template("index.html")

@app.route("/api/search", methods=["GET"])
def api_search():
    q = request.args.get("q", "")
    source = request.args.get("source", "").strip() or None
    mode = request.args.get("mode", "q")  # q = keyword, a = "asos topish"
    # mode ҳозирча бир хил: иккаласида ҳам q текстдан излайди

    results = score_query(q, source_filter=source, limit=25)
    return jsonify({"ok": True, "count": len(results), "results": results, "mode": mode})

@app.route("/api/sources", methods=["GET"])
def api_sources():
    sources = INDEX.get("sources", [])
    out = []
    for s in sources:
        out.append({"key": s, "label": SOURCE_LABELS.get(s, s)})
    return jsonify({"ok": True, "sources": out})

if __name__ == "__main__":
    # Локалда ишлатиш учун
    app.run(host="0.0.0.0", port=5000, debug=True)
