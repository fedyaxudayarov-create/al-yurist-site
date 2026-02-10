import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from flask import Flask, request, render_template_string

app = Flask(__name__)
HEADERS = {"User-Agent": "Mozilla/5.0 (AL-Yurist)"}

# Аниқ манбалар (doc_id) — шуниси вилоят қарорларини “кесади”
CATEGORIES = {
    "mehnat": {
        "title": "Меҳнат кодекси",
        "doc_id": "-6257288",
        "hint": "масалан: ишдан бўшатиш, меҳнат шартномаси, ишга қабул қилиш, интизомий жазо",
    },
    "mamuriy": {
        "title": "Маъмурий жавобгарлик",
        "doc_id": "-97664",
        "hint": "масалан: маъмурий ҳуқуқбузарлик, жарима, маъмурий жавобгарлик",
    },
    "jinoyat": {
        "title": "Жиноий жавобгарлик",
        "doc_id": "-111453",
        "hint": "масалан: жиноят таркиби, жазо, жавобгарлик",
    },
    "konst": {
        "title": "Конституция",
        "doc_id": "-6445145",
        "hint": "масалан: фуқаро ҳуқуқлари, давлат ҳокимияти, конституциявий норма",
    },
    "davxizm": {
        "title": "Давлат фуқаролик хизмати",
        "doc_id": "-6145972",
        "hint": "масалан: давлат хизматчиси, интизом, аттестация, лавозим",
    },
    "umumiy": {
        "title": "Қонун-қоидалар (умумий)",
        "doc_id": None,
        "hint": "масалан: қарор, фармойиш, низом (умумий қидирув)",
    },
}

# ===== Кирилл↔Лотин (содда, амалда ишлайдиган) =====
# Етарли “амалий” конверсия: HR матнларига ҳам тўғри келади.
LAT2CYR = [
    ("g‘", "ғ"), ("g'", "ғ"), ("o‘", "ў"), ("o'", "ў"),
    ("sh", "ш"), ("ch", "ч"), ("ng", "нг"),
    ("ya", "я"), ("yo", "ё"), ("yu", "ю"), ("ye", "е"),
    ("a", "а"), ("b", "б"), ("d", "д"), ("e", "е"), ("f", "ф"),
    ("g", "г"), ("h", "ҳ"), ("i", "и"), ("j", "ж"), ("k", "к"),
    ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"),
    ("q", "қ"), ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"),
    ("v", "в"), ("x", "х"), ("y", "й"), ("z", "з"),
]
CYR2LAT = [
    ("ғ", "g'"), ("ў", "o'"), ("ш", "sh"), ("ч", "ch"), ("нг", "ng"),
    ("я", "ya"), ("ё", "yo"), ("ю", "yu"), ("е", "e"),
    ("а", "a"), ("б", "b"), ("д", "d"), ("ф", "f"), ("г", "g"),
    ("ҳ", "h"), ("и", "i"), ("ж", "j"), ("к", "k"), ("л", "l"),
    ("м", "m"), ("н", "n"), ("о", "o"), ("п", "p"), ("қ", "q"),
    ("р", "r"), ("с", "s"), ("т", "t"), ("у", "u"), ("в", "v"),
    ("х", "x"), ("й", "y"), ("з", "z"),
]

def to_cyr(s: str) -> str:
    s2 = s
    lower = s2.lower()
    # ишончли: кичик ҳарфда айлантирамиз (HR учун етарли)
    out = lower
    for a, b in LAT2CYR:
        out = out.replace(a, b)
    return out

def to_lat(s: str) -> str:
    s2 = s
    out = s2
    for a, b in CYR2LAT:
        out = out.replace(a, b)
    return out

def norm_space(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

# ===== Lex helpers =====
DOC_CACHE = {}  # doc_id -> {"ts":..., "html":..., "articles":[...]}
CACHE_TTL = 6 * 60 * 60  # 6 соат

def fetch_doc_html(doc_id: str) -> str:
    """Кодекс матнини олиб келиб кэшлаймиз."""
    now = time.time()
    cached = DOC_CACHE.get(doc_id)
    if cached and (now - cached["ts"] < CACHE_TTL):
        return cached["html"]

    url = f"https://lex.uz/uz/docs/{doc_id}"
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    html = r.text
    DOC_CACHE[doc_id] = {"ts": now, "html": html, "articles": None}
    return html

def parse_articles(doc_id: str):
    """Кодекс саҳифасида 'Модда' блокларини ажратиб оламиз."""
    now = time.time()
    cached = DOC_CACHE.get(doc_id)
    if cached and cached.get("articles") is not None and (now - cached["ts"] < CACHE_TTL):
        return cached["articles"]

    html = fetch_doc_html(doc_id)
    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text("\n", strip=True)
    # “Модда 12.” каби жойларни тўплаймиз (хом усул, лекин ишлайди)
    # Саҳифа структураси ўзгарса ҳам шу regex кўп ҳолатда ёрдам беради
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    joined = "\n".join(lines)

    # Модда сарлавҳасини топиш (кирил/латин, русча 'Статья' ҳам бўлиши мумкин)
    pattern = re.compile(r"(Модда\s+\d+\.?|Статья\s+\d+\.?)", re.IGNORECASE)
    matches = list(pattern.finditer(joined))

    articles = []
    if matches:
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else min(len(joined), start + 2500)
            block = joined[start:end].strip()
            title = m.group(1)
            # қисқа сарлавҳа
            short = block.split("\n", 1)[0][:120]
            articles.append({
                "title": short if short else title,
                "block": block[:2200],
                "url": f"https://lex.uz/uz/docs/{doc_id}",
            })

    if doc_id in DOC_CACHE:
        DOC_CACHE[doc_id]["articles"] = articles
        DOC_CACHE[doc_id]["ts"] = now
    else:
        DOC_CACHE[doc_id] = {"ts": now, "html": html, "articles": articles}
    return articles

def search_inside_doc(doc_id: str, query: str, limit: int = 8):
    """Кодекснинг ўзида (модда блокларида) қидириш."""
    q = norm_space(query).lower()
    if not q:
        return []

    # икки ёзувни ҳам текширамиз: кирилл ва лотин
    q_c = to_cyr(q)
    q_l = to_lat(q)

    articles = parse_articles(doc_id)
    scored = []
    for a in articles:
        blob = a["block"].lower()
        score = 0
        if q in blob: score += 3
        if q_c and q_c in blob: score += 2
        if q_l and q_l in blob: score += 2
        # калит сўзлар бўйича майда балл
        for w in q.split():
            if len(w) >= 4 and w in blob:
                score += 1
        if score > 0:
            # қисқа snippet
            idx = blob.find(q) if q in blob else (blob.find(q_c) if q_c in blob else blob.find(q_l))
            if idx < 0: idx = 0
            snippet = a["block"][max(0, idx - 120): idx + 240]
            scored.append((score, a["title"], a["url"], snippet))

    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for s, title, url, snip in scored[:limit]:
        out.append({"title": title, "url": url, "snippet": snip})
    return out

def lex_general_search(query: str, limit: int = 10):
    """Умумий lex қидирув (меню 'умумий' учун)."""
    q = norm_space(query)
    if not q:
        return []
    url = "https://lex.uz/uz/search/loc?query=" + quote_plus(q)
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    res = []
    for a in soup.select("a[href^='/uz/docs/'], a[href^='/ru/docs/']"):
        title = a.get_text(" ", strip=True)
        href = a.get("href", "")
        if title and href:
            res.append({"title": title, "url": "https://lex.uz" + href})
        if len(res) >= limit:
            break
    return res

# ===== Матндан “асос” излаш (буйруқ/қарор) =====
STOP = set("""
ва ҳам ёки учун билан бўйича тўғрисида ҳақида асосида
туғрисидаги қилиниши қилиш қилиб қилинган қилинса
ҳаққидаги ҳамда шу бу у мазкур асоси асос
""".split())

def extract_keywords(text: str, max_words: int = 10):
    t = (text or "").lower()
    t = re.sub(r"[^a-zа-яёғқҳўʼ' \n\t-]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    words = [w for w in t.split() if len(w) >= 4 and w not in STOP]
    # энг кўп такрорланган сўзлар
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    top = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:max_words]
    return [w for w, _ in top]

def auto_category_from_text(text: str) -> str:
    t = (text or "").lower()
    if any(x in t for x in ["ишдан", "меҳнат", "ходим", "интизом", "шартнома", "таътил", "ишга"]):
        return "mehnat"
    if any(x in t for x in ["маъмурий", "жарима", "баённома", "ҳуқуқбузарлик"]):
        return "mamuriy"
    if any(x in t for x in ["жиноят", "жиноий", "қамоқ", "жазо"]):
        return "jinoyat"
    if any(x in t for x in ["конституция", "ҳуқуқ", "эркинлик", "давлат ҳокимияти"]):
        return "konst"
    if any(x in t for x in ["давлат хизмат", "фуқаролик хизмати", "аттестация"]):
        return "davxizm"
    return "umumiy"

HTML = """
<!doctype html>
<html lang="uz">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>AL Юрист</title>
<style>
:root{
  --bg:#0b1220;--card:#121b2f;--line:#253358;
  --text:#eaf0ff;--muted:#a9b6d6;--btn:#3b82f6;--in:#0c1428;
}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,Segoe UI,Arial;background:var(--bg);color:var(--text)}
.wrap{max-width:1100px;margin:auto;padding:18px 12px 40px}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap}
h1{margin:0;font-size:22px}
.small{color:var(--muted);font-size:12px}
.menu{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
.menu a{border:1px solid var(--line);background:var(--card);color:var(--text);text-decoration:none;
  padding:8px 10px;border-radius:12px;font-size:13px}
.menu a.active{background:var(--btn);border-color:var(--btn)}
.grid{display:grid;grid-template-columns:1fr;gap:12px}
.card{border:1px solid var(--line);background:var(--card);border-radius:16px;padding:14px}
label{display:block;color:var(--muted);font-size:12px;margin-bottom:6px}
textarea{width:100%;min-height:110px;background:var(--in);border:1px solid var(--line);
  border-radius:12px;padding:12px;color:var(--text);outline:none;resize:vertical}
textarea:focus{border-color:var(--btn)}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:10px}
.btn{border:none;background:var(--btn);color:#fff;padding:10px 14px;border-radius:12px;font-weight:800;cursor:pointer}
.btn2{border:1px solid var(--line);background:var(--in);color:var(--text);padding:10px 12px;border-radius:12px;cursor:pointer}
.btn2:hover{border-color:var(--btn)}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.chip{border:1px solid var(--line);background:var(--in);color:var(--text);padding:8px 10px;border-radius:999px;
  cursor:pointer;font-size:13px}
.chip:hover{border-color:var(--btn)}
.res{margin-top:12px}
.item{background:var(--in);border:1px solid var(--line);border-radius:14px;padding:12px;margin:10px 0}
.item a{color:#93c5fd;text-decoration:none}
.item a:hover{text-decoration:underline}
.snip{margin-top:8px;color:var(--muted);font-size:12px;white-space:pre-wrap}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.tab{border:1px solid var(--line);background:var(--in);color:var(--text);padding:8px 10px;border-radius:12px;cursor:pointer}
.tab.active{background:var(--btn);border-color:var(--btn)}
.hidden{display:none}
.warn{border:1px dashed var(--line);background:var(--in);border-radius:14px;padding:12px;color:var(--muted);font-size:12px}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <h1>AL Юрист</h1>
      <div class="small">Кодекс/қонун ичида “модда”га яқин жойларни топиб беради (lex.uz очиқ манба)</div>
    </div>
    <div class="small">Сичқонча шарт эмас: <b>Enter</b> босинг ✅</div>
  </div>

  <div class="menu">
    {% for k,v in categories.items() %}
      <a href="/?cat={{k}}&mode={{mode}}" class="{% if cat==k %}active{% endif %}">{{v.title}}</a>
    {% endfor %}
  </div>

  <div class="card">
    <div class="tabs">
      <button class="tab {% if mode=='q' %}active{% endif %}" onclick="goMode('q')">Қидирув (калит сўз)</button>
      <button class="tab {% if mode=='doc' %}active{% endif %}" onclick="goMode('doc')">Буйруқ/қарор матни (асос топиш)</button>
    </div>

    <div id="modeQ" class="{% if mode!='q' %}hidden{% endif %}">
      <form method="post" id="formQ">
        <input type="hidden" name="mode" value="q"/>
        <label>Калит сўз (қисқа ёзинг):</label>
        <textarea name="q" id="qBox" placeholder="{{ categories[cat].hint }}">{{ q }}</textarea>
        <div class="row">
          <button class="btn" type="submit">Қидириш</button>
          <button class="btn2" type="button" onclick="toggleScript('qBox')">Кирилл ↔ Лотин</button>
          <div class="small">Масалан: <b>ишдан бўшатиш</b>, <b>меҳнат шартномаси</b>, <b>интизомий жазо</b></div>
        </div>
        <div class="chips">
          <span class="chip" onclick="quick('ишдан бўшатиш')">Ишдан бўшатиш</span>
          <span class="chip" onclick="quick('ишга қабул қилиш')">Ишга қабул қилиш</span>
          <span class="chip" onclick="quick('меҳнат шартномаси')">Меҳнат шартномаси</span>
          <span class="chip" onclick="quick('интизомий жазо')">Интизомий жазо</span>
          <span class="chip" onclick="quick('таътил')">Таътил</span>
        </div>
      </form>
    </div>

    <div id="modeDoc" class="{% if mode!='doc' %}hidden{% endif %}">
      <form method="post" id="formDoc">
        <input type="hidden" name="mode" value="doc"/>
        <label>Буйруқ/қарор матнини шу ерга ташланг (сайт калит ибораларни ўзи ажратади):</label>
        <textarea name="doc" id="docBox" placeholder="Буйруқ (лойиҳа) матнини қўйинг...">{{ doc }}</textarea>
        <div class="row">
          <button class="btn" type="submit">Асосини топиш</button>
          <button class="btn2" type="button" onclick="toggleScript('docBox')">Кирилл ↔ Лотин</button>
          <div class="small">Кең матн ташланса ҳам бўлади. Натижа “модда” блокларига яқин жойлар билан чиқади.</div>
        </div>
      </form>
      {% if extracted %}
        <div class="warn" style="margin-top:10px">
          Ажратилган калит сўзлар: <b>{{ extracted|join(', ') }}</b><br/>
          Авто танланган йўналиш: <b>{{ categories[autocat].title }}</b> (хоҳласангиз юқори менюдан ўзингиз алмаштирасиз)
        </div>
      {% endif %}
    </div>

    <div class="res">
      {% if results is not none %}
        {% if results %}
          {% for r in results %}
            <div class="item">
              <a href="{{ r.url }}" target="_blank">{{ r.title }}</a>
              {% if r.snippet %}
                <div class="snip">{{ r.snippet }}</div>
              {% endif %}
              <div class="small">{{ r.url }}</div>
            </div>
          {% endfor %}
        {% else %}
          <div class="warn">Натижа топилмади. Калит сўзни қисқартириб ёзинг (масалан: <b>бўшатиш</b>).</div>
        {% endif %}
      {% endif %}
    </div>

    <div class="warn" style="margin-top:10px">
      Эслатма: бу демо. Натижа “асос” топишга ёрдам беради, лекин расмий қарор/буйруқ олдидан матнни ўзингиз ҳам текшириб чиқинг.
    </div>
  </div>
</div>

<script>
function goMode(m){
  const url = new URL(window.location.href);
  url.searchParams.set('mode', m);
  window.location.href = url.toString();
}
function quick(t){
  const box = document.getElementById('qBox');
  box.value = t;
  box.focus();
}
function toggleScript(id){
  const box = document.getElementById(id);
  const s = box.value || "";
  // оддий қоида: агар кирилл кўп бўлса -> лотинга, бўлмаса -> кириллга
  const cyr = (s.match(/[А-Яа-яЁёҒғҚқҲҳЎў]/g)||[]).length;
  if(cyr > 2){
    box.value = cyr2lat(s);
  }else{
    box.value = lat2cyr(s);
  }
}
function lat2cyr(s){
  let t = s.toLowerCase();
  const reps = [
    ["g‘","ғ"],["g'","ғ"],["o‘","ў"],["o'","ў"],
    ["sh","ш"],["ch","ч"],["ng","нг"],
    ["ya","я"],["yo","ё"],["yu","ю"],["ye","е"],
    ["a","а"],["b","б"],["d","д"],["e","е"],["f","ф"],
    ["g","г"],["h","ҳ"],["i","и"],["j","ж"],["k","к"],
    ["l","л"],["m","м"],["n","н"],["o","о"],["p","п"],
    ["q","қ"],["r","р"],["s","с"],["t","т"],["u","у"],
    ["v","в"],["x","х"],["y","й"],["z","з"]
  ];
  for(const [a,b] of reps){ t = t.split(a).join(b); }
  return t;
}
function cyr2lat(s){
  let t = s;
  const reps = [
    ["нг","ng"],["ғ","g'"],["ў","o'"],["ш","sh"],["ч","ch"],
    ["я","ya"],["ё","yo"],["ю","yu"],["е","e"],
    ["а","a"],["б","b"],["д","d"],["ф","f"],["г","g"],
    ["ҳ","h"],["и","i"],["ж","j"],["к","k"],["л","l"],
    ["м","m"],["н","n"],["о","o"],["п","p"],["қ","q"],
    ["р","r"],["с","s"],["т","t"],["у","u"],["в","v"],
    ["х","x"],["й","y"],["з","z"]
  ];
  for(const [a,b] of reps){ t = t.split(a).join(b); }
  return t;
}

// Enter -> submit (Shift+Enter янги қатор)
document.addEventListener('keydown', function(e){
  const active = document.activeElement;
  if(!active) return;
  if(active.id === 'qBox' && e.key === 'Enter' && !e.shiftKey){
    e.preventDefault();
    document.getElementById('formQ').submit();
  }
  if(active.id === 'docBox' && e.key === 'Enter' && e.ctrlKey){
    e.preventDefault();
    document.getElementById('formDoc').submit();
  }
});
</script>
</body>
</html>
"""

def search_results(cat_key: str, query: str):
    """Менюга қараб: кодекс ичида ёки умумий қидирув."""
    cat = CATEGORIES.get(cat_key, CATEGORIES["mehnat"])
    q = norm_space(query)
    if not q:
        return []

    # кодекс ичида “модда” блокларида қидириш
    if cat["doc_id"]:
        return search_inside_doc(cat["doc_id"], q, limit=8)

    # умумий қидирув
    g = lex_general_search(q, limit=10)
    # snippet йўқ — бир хил формат учун
    return [{"title": x["title"], "url": x["url"], "snippet": ""} for x in g]

@app.route("/", methods=["GET", "POST"])
def home():
    cat = request.args.get("cat", "mehnat")
    mode = request.args.get("mode", "q")  # q or doc

    q = ""
    doc = ""
    results = None
    extracted = []
    autocat = cat

    if request.method == "POST":
        mode = request.form.get("mode", mode)

        if mode == "q":
            q = request.form.get("q", "")
            results = search_results(cat, q)

        elif mode == "doc":
            doc = request.form.get("doc", "")
            extracted = extract_keywords(doc, max_words=10)
            autocat = auto_category_from_text(doc)

            # агар менюда кодекс танланган бўлса шуни қолдирамиз, акс ҳолда авто-категория
            use_cat = cat if cat in CATEGORIES else autocat
            if use_cat == "umumiy":
                use_cat = autocat

            # матндан чиқарилган калит сўзлардан бир нечта сўров қиламиз
            # биринчи навбатда 2-3 та энг кучлиси билан
            queries = extracted[:4] if extracted else [doc[:60]]
            merged = []
            seen = set()
            for qq in queries:
                for r in search_results(use_cat, qq):
                    key = (r["title"], r["url"])
                    if key not in seen:
                        seen.add(key)
                        merged.append(r)
                if len(merged) >= 10:
                    break
            results = merged[:10]

    return render_template_string(
        HTML,
        categories=CATEGORIES,
        cat=cat if cat in CATEGORIES else "mehnat",
        mode=mode,
        q=q,
        doc=doc,
        results=results,
        extracted=extracted,
        autocat=autocat if autocat in CATEGORIES else "mehnat",
    )

# ===== Матндан калит сўз чиқариш (юқорида ишлатилди) =====
STOP = set("""
ва ҳам ёки учун билан бўйича тўғрисида ҳақида асосида
туғрисидаги қилиниши қилиш қилиб қилинган қилинса
ҳаққидаги ҳамда шу бу у мазкур асоси асос
""".split())

def extract_keywords(text: str, max_words: int = 10):
    t = (text or "").lower()
    t = re.sub(r"[^a-zа-яёғқҳўʼ' \n\t-]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    words = [w for w in t.split() if len(w) >= 4 and w not in STOP]
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    top = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:max_words]
    return [w for w, _ in top]

def auto_category_from_text(text: str) -> str:
    t = (text or "").lower()
    if any(x in t for x in ["меҳнат", "ходим", "ишга", "ишдан", "шартнома", "интизом", "таътил"]):
        return "mehnat"
    if any(x in t for x in ["маъмурий", "жарима", "баённома", "ҳуқуқбузарлик"]):
        return "mamuriy"
    if any(x in t for x in ["жиноят", "жиноий", "жазо", "айб"]):
        return "jinoyat"
    if any(x in t for x in ["конституция", "ҳуқуқ", "эркинлик", "давлат ҳокимияти"]):
        return "konst"
    if any(x in t for x in ["давлат хизмат", "фуқаролик хизмати", "аттестация", "лавозим"]):
        return "davxizm"
    return "umumiy"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
