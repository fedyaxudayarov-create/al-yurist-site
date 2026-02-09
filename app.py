import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from flask import Flask, request, render_template_string

app = Flask(__name__)

HEADERS = {
    "User-Agent": "AL-Yurist/1.0 (demo; lex.uz based)"
}

HTML = """
<!doctype html>
<html lang="uz">
<head>
    <meta charset="utf-8">
    <title>AL Юрист</title>
</head>
<body style="font-family: Arial; max-width: 900px; margin: 30px auto;">
    <h2>AL Юрист — lex.uz асосида қонун ва модда топиш</h2>

    <form method="post">
        <textarea name="q" rows="6" style="width:100%;"
        placeholder="Буйруқ ёки саволни киритинг.
Масалан: Ходимни интизомий жазо билан ишдан бўшатиш мумкинми?">{{ q }}</textarea>
        <br><br>
        <button type="submit">Асосини топиш</button>
    </form>

    {% if results is not none %}
        <hr>
        <h3>Топилган ҳуқуқий асослар:</h3>

        {% if results %}
            <ol>
            {% for r in results %}
                <li>
                    <a href="{{ r.url }}" target="_blank">{{ r.title }}</a>
                </li>
            {% endfor %}
            </ol>
            <p><b>Эслатма:</b> Манба — lex.uz. Бу умумий ҳуқуқий маълумот.</p>
        {% else %}
            <p>Ҳеч нарса топилмади. Калит сўзни қисқартириб кўринг
            (масалан: <i>ишдан бўшатиш</i>).</p>
        {% endif %}
    {% endif %}
</body>
</html>
"""

def lex_search(text: str, limit: int = 7):
    tokens = re.findall(r"[а-яёa-z]+", text.lower())

    stop_words = {
        "қайси", "модда", "қандай", "тўғрими", "мумкинми",
        "деб", "мен", "керак", "бўлади", "қилиш"
    }

    tokens = [t for t in tokens if t not in stop_words]
    query = " ".join(tokens[:3]) if tokens else text

    url = f"https://lex.uz/uz/search/loc?query={quote_plus(query)}"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    results = []
    for a in soup.select("a"):
        href = a.get("href", "")
        if href.startswith("/uz/docs/"):
            title = a.get_text(" ", strip=True)
            full_url = "https://lex.uz" + href
            if title and full_url not in [x["url"] for x in results]:
                results.append({"title": title, "url": full_url})
        if len(results) >= limit:
            break

    return results

@app.route("/", methods=["GET", "POST"])
def home():
    q = ""
    results = None

    if request.method == "POST":
        q = request.form.get("q", "")
        if q.strip():
            results = lex_search(q)
        else:
            results = []

    return render_template_string(HTML, q=q, results=results)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
