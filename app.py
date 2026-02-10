import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from flask import Flask, request, render_template_string

app = Flask(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (AL-Yurist demo)"}

# Асосий очиқ манбалар (lex.uz) — тез кириш учун
SOURCES = [
    ("mehnat", "Меҳнат кодекси (2022)", "https://lex.uz/ru/docs/-6257288"),
    ("jinoyat", "Жиноят кодекси", "https://lex.uz/docs/-111453"),
    ("mamuriy", "Маъмурий жавобгарлик тўғрисидаги кодекс", "https://lex.uz/docs/-97664"),
    ("konst", "Конституция (2023)", "https://lex.uz/docs/-6445145"),
    ("fuqarolik", "Фуқаролик кодекси", "https://lex.uz/docs/-111189"),
    ("davxizm", "«Давлат фуқаролик хизмати тўғрисида» Қонун", "https://lex.uz/docs/-6145972"),
]

HTML = """
<!doctype html>
<html lang="uz">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>AL Юрист</title>
  <style>
    :root{
      --bg:#0b1220; --card:#121b2f; --line:#253358;
      --text:#eaf0ff; --muted:#a9b6d6; --btn:#3b82f6;
    }
    *{box-sizing:border-box}
    body{margin:0;font-family:system-ui,Segoe UI,Arial;background:var(--bg);color:var(--text)}
    .wrap{max-width:980px;margin:0 auto;padding:22px 14px 40px}
    .top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px}
    h1{margin:0;font-size:22px}
    .badge{border:1px solid var(--line);color:var(--muted);padding:6px 10px;border-radius:999px;font-size:12px}
    .grid{display:grid;grid-template-columns:1.35fr .65fr;gap:12px}
    @media (max-width:900px){.grid{grid-template-columns:1fr}}
    .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}
    .label{color:var(--muted);font-size:12px;margin-bottom:8px}
    textarea{width:100%;min-height:120px;background:#0c1428;border:1px solid var(--line);
      border-radius:12px;padding:12px;color:var(--text);outline:none;resize:vertical}
    textarea:focus{border-color:var(--btn)}
    .row{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px;align-items:center}
    .btn{border:none;background:var(--btn);color:#fff;padding:10px 14px;border-radius:12px;font-weight:700;cursor:pointer}
    .btn:hover{filter:brightness(1.05)}
    .hint{color:var(--muted);font-size:12px;line-height:1.35}
    .chips{display:flex;flex-wrap:wrap;gap:8px}
    .chip{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:8px 10px;
      color:var(--text);text-decoration:none;background:#0c1428;font-size:13px}
    .chip:hover{border-color:var(--btn)}
    .results{margin-top:12px}
    .res{border:1px solid var(--line);border-radius:14px;padding:12px;margin:10px 0;background:#0c1428}
    .res a{color:#93c5fd;text-decoration:none}
    .res a:hover{text-decoration:underline}
    .small{color:var(--muted);font-size:12px;margin-top:6px}
    .empty{border:1px dashed var(--line);border-radius:14px;padding:12px;color:var(--muted);background:#0c1428}
    .footer{margin-top:16px;color:var(--muted);font-size:12px}
    .k{font-weight:700}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div>
        <h1>AL Юрист — lex.uz асосида қонун/модда топиш</h1>
        <div class="small">HR буйруқ/қарор ёзаётганда “асос”ни тез топиш учун демо</div>
      </div>
      <div class="badge">Free demo</div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="label">Савол ёки калит сўз (қисқа ёзинг):</div>
        <form method="post">
          <textarea name="q" placeholder="Масалан: ишдан бўшатиш, интизомий жазо, меҳнат шартномасини бекор қилиш...">{{ q }}</textarea>
          <div class="row">
            <button class="btn" type="submit">Қидириш</button>
            <div class="hint">
              Масалан: <span class="k">бўшатиш</span>, <span class="k">интизом</span>, <span class="k">шартнома</span>, <span class="k">маъмурий жавобгарлик</span>
            </div>
          </div>
        </form>

        <div class="results">
          <div class="label">Топилган натижалар:</div>

          {% if results is not none %}
            {% if results %}
              {% for r in results %}
                <div class="res">
                  <a href="{{ r.url }}" target="_blank">{{ r.title }}</a>
                  <div class="small">{{ r.url }}</div>
                </div>
              {% endfor %}
              <div class="small">Эслатма: натижалар lex.uz қидирувидан олинади.</div>
            {% else %}
              <div class="empty">Ҳеч нарса топилмади. Калит сўзни қисқартириб кўринг (масалан: <b>бўшатиш</b>).</div>
            {% endif %}
          {% endif %}
        </div>
      </div>

      <div class="card">
        <div class="label">Асосий қонунлар (тез кириш):</div>
        <div class="chips">
          {% for key,title,url in sources %}
            <a class="chip" href="{{ url }}" target="_blank">{{ title }}</a>
          {% endfor %}
        </div>
        <div class="footer">
          Кейинги босқичда: ҳар бир кодекс матнидан тўғридан-тўғри қидириш (моддагача) қўшамиз.
        </div>
      </div>
    </div>

    <div class="footer">© AL Юрист — демо (очиқ манба: lex.uz)</div>
  </div>
</body>
</html>
"""

def normalize_query(q: str) -> str:
    q = (q or "").strip()
    q = re.sub(r"\s+", " ", q)
    # Оддий нормализация: ишдан бўшатилди/бўшатилади -> бўшатиш
    q = q.replace("бўшатилади", "бўшатиш").replace("бўшатилди", "бўшатиш")
    return q

def lex_search(query: str, limit: int = 10):
    q = normalize_query(query)
    if not q:
        return []

    url = f"https://lex.uz/uz/search/loc?query={quote_plus(q)}"
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    results = []
    for a in soup.select("a[href^='/uz/docs/'], a[href^='/ru/docs/']"):
        href = a.get("href", "")
        title = a.get_text(" ", strip=True)
        if not title:
            continue
        full = "https://lex.uz" + href
        if full not in {x["url"] for x in results}:
            results.append({"title": title, "url": full})
        if len(results) >= limit:
            break
    return results

@app.route("/", methods=["GET", "POST"])
def home():
    q = ""
    results = None
    if request.method == "POST":
        q = request.form.get("q", "")
        results = lex_search(q, limit=10)
    return render_template_string(HTML, q=q, results=results, sources=SOURCES)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
