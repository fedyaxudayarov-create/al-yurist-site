import sqlite3
from pathlib import Path
from flask import Flask, render_template, request, jsonify

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "lex_index.db"

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def search_fts(text, cat):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Категория бўйича филтрлаш ва қидириш
    query = """
        SELECT items.* FROM items 
        JOIN items_fts ON items.id = items_fts.rowid 
        WHERE items_fts MATCH ? AND items.code_key = ?
        LIMIT 10
    """
    # Агар категория 'all' бўлса ёки филтрсиз қидирмоқчи бўлсангиз, сўровни ўзгартириш мумкин
    rows = cur.execute(query, (text, cat)).fetchall()
    conn.close()
    
    results = []
    for row in rows:
        results.append({
            "source_label": row["code_title"],
            "modda": row["article_no"],
            "title": row["title"],
            "snippet": row["text"][:400] + "..." if len(row["text"]) > 400 else row["text"]
        })
    return results

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    cat = (data.get("cat") or "mehnat").strip()

    if not text:
        return jsonify({"ok": False, "error": "Матн киритилмаган", "results": []}), 400

    try:
        # Хатолик шу ерда эди: search_fts функцияси энди таърифланган
        results = search_fts(text, cat)
        return jsonify({"ok": True, "results": results})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "results": []}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
