# app.py нинг энг бошига қўшиш мумкин:
import os
os.environ["GOOGLE_API_USE_MTLS_ENDPOINT"] = "never"
import sqlite3
import google.generativeai as genai
from pathlib import Path
from flask import Flask, render_template, request, jsonify

# app.py ичидаги мана шу қаторни топинг ва алмаштиринг:
API_KEY = "AIzaSyADOBxK551UG6yAyl_u3o_VFm0bSRKv6YY"
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('models/gemini-1.5-flash')
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "lex_index.db"

app = Flask(__name__)

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

@app.route("/")
def home():
    return render_template("index.html", categories=CATEGORIES, cat="mehnat", mode="q")

@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    cat = data.get("cat", "mehnat")

    if not text:
        return jsonify({"ok": False, "error": "Матн киритилмаган"})

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Базадан қидириш
        search_query = " AND ".join(text.split())
        query = "SELECT * FROM items JOIN items_fts ON items.id = items_fts.rowid WHERE items_fts MATCH ? AND code_key = ? LIMIT 3"
        rows = cur.execute(query, (search_query, cat)).fetchall()
        
        results = []
        context_for_ai = ""
        
        for row in rows:
            results.append({
                "code_title": row["code_title"],
                "article_no": row["article_no"],
                "title": row["title"],
                "snippet": row["text"], # Тўлиқ матнни чиқарамиз
                "url": row["url"] or "https://lex.uz"
            })
            context_for_ai += f"\nМодда {row['article_no']}: {row['text']}\n"
        
        # 2. Агар маълумот топилса, Gemini-дан шарҳ сўраймиз
        ai_comment = ""
        if results:
            prompt = f"Сен профессионал юристсан. Қуйидаги қонун матнига асосланиб, фойдаланувчининг '{text}' деган сўровига қисқа ва аниқ тушунтириш бер:\n{context_for_ai}"
            response = model.generate_content(prompt)
            ai_comment = response.text

        conn.close()
        return jsonify({"ok": True, "results": results, "ai_comment": ai_comment})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)







