import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from flask import Flask, request, render_template_string

app = Flask(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (AL-Yurist)"}

CATEGORIES = {
    "mehnat": {
        "title": "Меҳнат кодекси",
        "hint": "ишга қабул қилиш, ишдан бўшатиш, меҳнат шартномаси",
        "lex": "https://lex.uz/uz/search/loc?query="
    },
    "qonun": {
        "title": "Қонун қоидалар (умумий)",
        "hint": "қонун, қарор, фармойиш",
        "lex": "https://lex.uz/uz/search/loc?query="
    },
    "mamuriy": {
        "title": "Маъмурий жавобгарлик",
        "hint": "жарима, маъмурий жавобгарлик",
        "lex": "https://lex.uz/uz/search/loc?query="
    },
    "jinoyat": {
        "title": "Жиноий жавобгарлик",
        "hint": "жиноят таркиби, жавобгарлик",
        "lex": "https://lex.uz/uz/search/loc?query="
    },
    "konst": {
        "title": "Конституция",
        "hint": "фуқаро ҳуқуқлари, давлат",
        "lex": "https://lex.uz/uz/search/loc?query="
    },
    "davxizm": {
        "title": "Давлат фуқаролик хизмати",
        "hint": "давлат хизматчиси, хизмат ўташ",
        "lex": "https://lex.uz/uz/search/loc?query="
    }
}

HTML = """
<!doctype html>
<html lang="uz">
<head>
<meta charset="utf-8">
<title>AL Юрист</title>
<style>
body{margin:0;font-family:Arial;background:#0b1220;color:#eaf0ff}
.wrap{max-width:1000px;margin:auto;padding:20px}
h1{margin-bottom:10px}
.menu{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:15px}
.menu a{padding:8px 12px;border-radius:10px;
background:#121b2f;color:#fff;text-decoration:none;border:1px solid #253358}
.menu a.active{background:#3b82f6}
.card{background:#121b2f;border:1px solid #253358;border-radius:14px;padding:15px}
textarea{width:100%;min-height:110px;background:#0c1428;
border:1px solid #253358;border-radius:10px;color:#fff;padding:10px}
button{margin-top:10px;padding:10px 16px;border:none;
background:#3b82f6;color:#fff;border-radius:10px;font-weight:bold;cursor:pointer}
.result{margin-top:15px}
.item{background:#0c1428;border:1px solid #253358;
border-radius:10px;padding:10px;margin-bottom:10px}
.item a{color:#93c5fd;text-decoration:none}
.small{color:#a9b6d6;font-size:12px}
</style>
</head>
<body>
<div class="wrap">
<h1>AL Юрист</h1>
<div class="small">Қонун ва кодекслар бўйича тезкор қидирув (lex.uz)</div>

<div class="menu">
{% for k,v in categories.items() %}
<a href="/?cat={{k}}" class="{% if cat==k %}active{% endif %}">{{v.title}}</a>
{% endfor %}
</div>

<div class="card">
<form method="post">
<textarea name="q" placeholder="{{ categories[cat].hint }}">{{ q }}</textarea>
<button>Қидириш</button>
</form>

<div class="result">
{% if results %}
{% for r in results %}
<div class="item">
<a href="{{r.url}}" target="_blank">{{r.title}}</a>
<div class="small">{{r.url}}</div>
</div>
{% endfor %}
{% elif searched %}
<div class="small">Натижа топилмади. Калит сўзни қисқартириб кўринг.</div>
{% endif %}
</div>
</div>
</div>
</body>
</html>
"""

def lex_search(base, q):
    url = base + quote_plus(q)
    r = requests.get(url, headers=HEADERS, timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")
    res = []
    for a in soup.select("a[href^='/uz/docs/'],a[href^='/ru/docs/']")[:10]:
        res.append({
            "title": a.get_text(" ", strip=True),
            "url": "https://lex.uz" + a["href"]
        })
    return res

@app.route("/", methods=["GET", "POST"])
def home():
    cat = request.args.get("cat", "mehnat")
    q = ""
    results = []
    searched = False

    if request.method == "POST":
        q = request.form.get("q", "")
        searched = True
        if q:
            results = lex_search(CATEGORIES[cat]["lex"], q)

    return render_template_string(
        HTML,
        categories=CATEGORIES,
        cat=cat,
        q=q,
        results=results,
        searched=searched
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
