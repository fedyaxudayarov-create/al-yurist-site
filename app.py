import os
import re
import json
import sqlite3
from pathlib import Path
from flask import Flask, render_template, request, jsonify

from rapidfuzz import fuzz

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "data" / "lex_index.db"
HR_PATH = APP_DIR / "data" / "hr_templates.json"

app = Flask(__name__)

CATEGORIES = [
    {"key": "mehnat", "title": "Меҳнат кодекси"},
    {"key": "jinoyat", "title": "Жиноий жавобгарлик (ЖК)"},
    {"key": "mamuriy", "title": "Маъмурий жавобгарлик (МЖтК)"},
    {"key": "konstitutsiya", "title": "Конституция"},
    {"key": "fuqarolik", "title": "Фуқаролик кодекси"},
    {"key": "davlat_xizmati", "title": "Давлат фуқаролик хизмати"},
    {"key": "umumiy", "title": "Қонун-қоидалар (умумий)"},
    {"key": "hr", "title": "HR шаблонлар"},
]

def get_conn():
    if not DB_PATH.exists():
        raise RuntimeError(f"База топилмади: {DB_PATH}. Аввал build_index.py ишга туширинг.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def load_hr():
    if not HR_PATH.exists():
        return []
    return json.loads(HR_PATH.read_text(encoding="utf-8"))

def normalize_query(q: str) -> str:
    q = (q or "").strip()
    q = re.sub(r"\s+", " ", q)
    return q

def extract_keywords(text: str, max_words: int = 12):
    """
    Буйруқ/қарор матнидан калит сўзларни оддий усулда ажратиб оламиз.
    (кейинчалик NLP билан кучайтириш мумкин)
    """
    text = normalize_query(text).lower()
    # ўзбек/рус ҳарфлари + сонларни қолдирамиз
    words = re.findall(r"[a-zа-яёўқғҳ]+", text, flags=re.IGNORECASE)
    stop = set(["ва", "ҳам", "учун", "билан", "ёки", "буйруқ", "қарор", "№", "сонли", "тўғрисида",
                "the", "and", "for", "with", "о", "об", "по", "в", "на", "и", "или", "это"])
    freq = {}
    for w in words:
        if len(w) < 4:
            continue
        if w in stop:
            continue
        freq[w] = freq.get(w, 0) + 1
    # энг кўп учраганлар
    kws = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:max_words]
    return [k for k, _ in kws]

def search_fts(q: str, code_key: str, limit: int = 15):
    q = normalize_query(q)
    if not q:
        return []

    conn = get_conn()
    try:
        cur = conn.cursor()

        # категория фильтри
        where = ""
        params = {}

        # "umumiy" — барчасидан қидиради
        if code_key and code_key not in ("umumiy", "hr"):
            where = "WHERE code_key = :ck"
            params["ck"] = code_key

        # FTS запрос: сўзларга бўлиб, prefix қидириш
        tokens = [t for t in re.split(r"\s+", q) if t]
        fts_q = " AND ".join([f'{t}*' for t in tokens[:8]])

        sql = f"""
        SELECT i.code_title, i.article_no, i.title, i.text, i.url
        FROM items_fts f
        JOIN items i ON i.id = f.rowid
        WHERE items_fts MATCH :fts
        """
        params["fts"] = fts_q

        if where:
            sql += f" AND i.code_key = :ck"

        sql += " LIMIT :lim"
        params["lim"] = limit

        rows = cur.execute(sql, params).fetchall()
        results = []
        for r in rows:
            snippet = r["text"][:450] + ("..." if len(r["text"]) > 450 else "")
            results.append({
                "code_title": r["code_title"],
                "article_no": r["article_no"] or "",
                "title": r["title"],
                "snippet": snippet,
                "url": r["url"],
            })
        return results
    finally:
        conn.close()

def search_hr(q: str, limit: int = 10):
    q = normalize_query(q).lower()
    items = load_hr()
    scored = []
    for it in items:
        hay = (it.get("title","") + " " + " ".join(it.get("tags", [])) + " " + it.get("text","")).lower()
        score = fuzz.partial_ratio(q, hay) if q else 0
        scored.append((score, it))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for score, it in scored[:limit]:
        out.append({
            "title": it["title"],
            "snippet": it["text"][:450] + ("..." if len(it["text"]) > 450 else ""),
            "full": it["text"]
        })
    return out

@app.get("/")
def index():
    cat = request.args.get("cat", "mehnat")
    mode = request.args.get("mode", "q")  # q=калит сўз, doc=буйруқ матни
    return render_template("index.html", categories=CATEGORIES, cat=cat, mode=mode)

@app.post("/api/search")
def api_search():
    payload = request.get_json(force=True, silent=True) or {}
    cat = payload.get("cat", "mehnat")
    mode = payload.get("mode", "q")
    text = payload.get("text", "")

    if cat == "hr":
        return jsonify({"ok": True, "results": search_hr(text)})

    if mode == "doc":
        kws = extract_keywords(text)
        # калит сўзлардан битта query ясаймиз
        q = " ".join(kws[:8])
        results = search_fts(q, cat)
        return jsonify({"ok": True, "keywords": kws, "query": q, "results": results})

    # mode == "q"
    results = search_fts(text, cat)
    return jsonify({"ok": True, "results": results})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), debug=True)
