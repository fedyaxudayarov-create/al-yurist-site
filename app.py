import os
import sqlite3
from pathlib import Path

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from openai import OpenAI

# .env ни ўқиш (OPENAI_API_KEY шу ердан олинади)
load_dotenv()

# OpenAI клиента (калит OPENAI_API_KEY орқали автомат ўқилади)
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

OPENAI_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

# Агар хоҳласангиз .env га OPENAI_MODEL ҳам қўшиб бошқаришингиз мумкин
# Масалан: OPENAI_MODEL=gpt-5.2
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")

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
    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({"ok": False, "error": "Матн киритилмаган"})

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 1) Базадан қидириш (ҳозирча LIKE қолдирдик)
        query = "SELECT * FROM items WHERE text LIKE ? LIMIT 3"
        rows = cur.execute(query, (f"%{text}%",)).fetchall()

        results = []
        context_text = ""
        for row in rows:
            results.append(
                {
                    "code_title": row["code_title"],
                    "article_no": row["article_no"],
                    "snippet": row["text"],
                    "url": "https://lex.uz",
                }
            )
            context_text += f"Модда {row['article_no']}: {row['text']}\n\n"

        # 2) OpenAI — қонун моддалари асосида изоҳ
        if results:
            prompt = (
                "Сен тажрибали юристсан. Фақат қуйида берилган қонун моддалари матнига таяниб жавоб бер.\n"
                "Агар маълумот етарли бўлмаса, 'моддаларда аниқ жавоб йўқ' деб айт ва қандай маълумот кераклигини сўра.\n\n"
                f"САВОЛ: {text}\n\n"
                f"МОДДАЛАР МАТНИ:\n{context_text}"
            )

            # Responses API (тавсия қилинади)
            response = client.responses.create(
                model=OPENAI_MODEL,
                instructions="Жавобни ўзбек (кирилл) тилида, тушунарли ва қисқа-аниқ бер.",
                input=prompt,
            )
            ai_comment = response.output_text
        else:
            ai_comment = "Кечирасиз, базадан бу мавзуга оид аниқ модда топилмади."

        conn.close()
        return jsonify({"ok": True, "results": results, "ai_comment": ai_comment})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

