import sqlite3
from pathlib import Path
from flask import Flask, render_template, request, jsonify

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "lex_index.db"

app = Flask(__name__)

# Сизнинг index.html даги тугмачалар учун категориялар рўйхати
CATEGORIES = [
    {"key": "mehnat", "title": "Меҳнат кодекси"},
    {"key": "jinoyat", "title": "Жиноят кодекси"},
    {"key": "mamuriy", "title": "Маъмурий кодекс"},
    {"key": "konstitutsiya", "title": "Конституция"},
    {"key": "fuqarolik", "title": "Фуқаролик кодекси"},
    {"key": "davlat_xizmati", "title": "Давлат хизмати"}
]

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/", methods=["GET"])
def home():
    # index.html кутаётган категорияларни юборамиз
    current_cat = request.args.get("cat", "mehnat")
    current_mode = request.args.get("mode", "q")
    return render_template("index.html", categories=CATEGORIES, cat=current_cat, mode=current_mode)

@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    cat = (data.get("cat") or "mehnat").strip()

    if not text:
        return jsonify({"ok": False, "error": "Матн бўш"}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Қидирув сўрови (FTS5 технологияси билан)
        # Агар матнда иккита сўз бўлса, уларни 'AND' билан боғлаймиз
        search_query = " AND ".join(text.split())
        
        query = """
            SELECT items.* FROM items 
            JOIN items_fts ON items.id = items_fts.rowid 
            WHERE items_fts MATCH ? AND items.code_key = ?
            LIMIT 15
        """
        rows = cur.execute(query, (search_query, cat)).fetchall()
        conn.close()

        results = []
        for row in rows:
            results.append({
                "code_title": row["code_title"],
                "article_no": row["article_no"],
                "title": row["title"],
                "snippet": row["text"][:450] + "...",
                "url": row["url"] if row["url"] else "https://lex.uz"
            })
        
        return jsonify({"ok": True, "results": results})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
