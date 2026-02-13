import os
import sqlite3
import google.generativeai as genai
from pathlib import Path
from flask import Flask, render_template, request, jsonify

# app.py ичидаги 7- ва 9-қаторлар шундай бўлсин:
API_KEY = "AIzaSyCeGHX0R07WPcBaM9F1WoN3TINuWTFaYNM"
model = genai.GenerativeModel('gemini-1.5-flash')

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "lex_index.db"

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    
    if not text:
        return jsonify({"ok": False, "error": "Матн киритилмаган"})

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Базадан қидириш
        query = "SELECT * FROM items WHERE text LIKE ? LIMIT 3"
        rows = cur.execute(query, (f"%{text}%",)).fetchall()
        
        results = []
        context_text = ""
        for row in rows:
            results.append({
                "code_title": row["code_title"],
                "article_no": row["article_no"],
                "snippet": row["text"],
                "url": "https://lex.uz"
            })
            context_text += f"Модда {row['article_no']}: {row['text']}\n\n"
        
        # 2. Gemini AI - энг барқарор 'gemini-pro' версияси
        ai_comment = ""
        if results:
            # Биз 'models/' префиксини қўшиб, энг ишончли моделни танладик
            model = genai.GenerativeModel('models/gemini-pro')
            prompt = f"Сен юристсан. Қуйидаги қонун моддаларига асосланиб саволга жавоб бер: {text}\n\nМатн:\n{context_text}"
            response = model.generate_content(prompt)
            ai_comment = response.text
        else:
            ai_comment = "Кечирасиз, базадан бу мавзуга оид аниқ модда топилмади."

        conn.close()
        return jsonify({"ok": True, "results": results, "ai_comment": ai_comment})

    except Exception as e:
        # Хатоликни экранга чиқариш
        return jsonify({"ok": False, "error": str(e)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)


