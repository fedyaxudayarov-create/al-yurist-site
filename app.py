# app.py
# -*- coding: utf-8 -*-
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

# ====== 1) Манбалар (lex.uz ҳужжатлари) ======
SOURCES: Dict[str, Dict[str, str]] = {
    "mehnat": {
        "title": "Меҳнат кодекси (2022)",
        "url": "https://lex.uz/ru/docs/-6257288",
    },
    "jinoyat": {
        "title": "Жиноят кодекси",
        "url": "https://lex.uz/ru/docs/-111453",
    },
    "mamuriy": {
        "title": "Маъмурий жавобгарлик тўғрисидаги кодекс",
        "url": "https://lex.uz/uz/docs/97664",
    },
    "konstitutsiya": {
        "title": "Конституция (2023)",
        "url": "https://lex.uz/docs/-6445145?otherlang=1",
    },
    "fuqarolik": {
        "title": "Фуқаролик кодекси",
        "url": "https://lex.uz/docs/-180552",
    },
    "dfx": {
        "title": "«Давлат фуқаролик хизмати тўғрисида» Қонун",
        "url": "https://lex.uz/ru/docs/-6145972",
    },
    # Умумий — бир нечта манбада қидиради (кодлар+асосийлар)
    "umumiy": {
        "title": "Қонун-кодекслар (умумий)",
        "url": "",
    },
}

DEFAULT_ORDER = ["mehnat", "dfx", "mamuriy", "jinoyat", "konstitutsiya", "fuqarolik"]

# ====== 2) Кичик кэш (Render free учун) ======
@dataclass
class CachedDoc:
    html: str
    fetched_at: float

DOC_CACHE: Dict[str, CachedDoc] = {}
CACHE_TTL_SEC = 60 * 30  # 30 дақиқа

HEADERS = {
    "User-Agent": "Mozilla/5.0 (AL-Yurist demo; +https://example.local) AppleWebKit/537.36"
}

STOPWORDS_UZ = set("""
ва ёки ҳам аммо учун билан бўйича тўғрисида мазкур ушбу шу бу ана у улар сиз биз мен сен
қилади қилиш қилинган этилади этилган бўлса бўлади керак шарт мумкин эмас
ҳақида асосида бўлган бўлгани бўлганда қилинса қилинг
""".split())

def fetch_html(url: str) -> str:
    now = time.time()
    cached = DOC_CACHE.get(url)
    if cached and (now - cached.fetched_at) < CACHE_TTL_SEC:
        return cached.html

    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    html = r.text
    DOC_CACHE[url] = CachedDoc(html=html, fetched_at=now)
    return html

def clean_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def extract_blocks_from_lex(html: str) -> List[Tuple[str, str]]:
    """
    Lex.uz ҳужжатидан блоклар чиқарамиз.
    Мақсад: '###-modda' атрофида матнларни блок қилиб, қидиришда шу блокни қайтариш.
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1) Кўп ҳолатда асосий матн body ичида; script/style ни олиб ташлаймиз
    for t in soup(["script", "style", "noscript"]):
        t.decompose()

    text = soup.get_text("\n")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text).strip()

    # 2) Моддаларни ажратиш: "123-modda" / "123-модда" турлари
    # Кирилл/лотин аралаш келиши мумкин, шунинг учун иккаласига regex
    pattern = re.compile(r"(?P<head>\b\d{1,4}\s*[-–]\s*(modda|модда)\b)", re.IGNORECASE)

    matches = list(pattern.finditer(text))
    if not matches:
        # Агар модда топилмаса — бутун матнни 1 блок қиламиз
        return [("Ҳужжат", text[:25000])]

    blocks: List[Tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        head = clean_text(m.group("head"))
        chunk = clean_text(text[start:end])
        # Жуда катта бўлса кесамиз (демо учун)
        if len(chunk) > 12000:
            chunk = chunk[:12000] + " …"
        blocks.append((head, chunk))
    return blocks

def find_matches_in_blocks(query: str, blocks: List[Tuple[str, str]], limit: int = 8) -> List[Dict]:
    q = query.strip()
    if not q:
        return []

    # “сўз”ларни қидириш: кирилл/лотин, катта-кичик фарқламасин
    q_norm = q.lower()

    results = []
    for head, chunk in blocks:
        if q_norm in chunk.lower():
            # match атрофидан 250 символ preview
            idx = chunk.lower().find(q_norm)
            left = max(0, idx - 120)
            right = min(len(chunk), idx + 120)
            preview = chunk[left:right]
            preview = preview.replace("\n", " ")
            results.append({
                "modda": head,
                "preview": ("…" if left > 0 else "") + preview + ("…" if right < len(chunk) else ""),
                "text": chunk
            })
            if len(results) >= limit:
                break
    return results

def extract_keywords_from_text(text: str, max_keywords: int = 6) -> List[str]:
    """
    Буйруқ/қарор матнидан калит сўзларни оддий усулда чиқарамиз:
    - 3+ ҳарфли сўзлар
    - stopword эмас
    - частота юқори
    """
    text = text.lower()
    # кирилл + лотин ҳарфлар
    words = re.findall(r"[a-zа-яёўқғҳ]{3,}", text, flags=re.IGNORECASE)
    freq: Dict[str, int] = {}
    for w in words:
        w = w.strip().lower()
        if w in STOPWORDS_UZ:
            continue
        freq[w] = freq.get(w, 0) + 1

    # энг кўп учраганлар
    ranked = sorted(freq.items(), key=lambda x: (-x[1], -len(x[0])))
    return [w for w, _ in ranked[:max_keywords]]

def search_one_source(cat: str, query: str) -> Dict:
    src = SOURCES.get(cat)
    if not src:
        return {"category": cat, "title": cat, "items": [], "error": "unknown category"}

    if cat == "umumiy":
        # умумий: бир нечта базада кетма-кет излаймиз
        merged = []
        for c in DEFAULT_ORDER:
            one = search_one_source(c, query)
            if one.get("items"):
                merged.append(one)
        return {"category": "umumiy", "title": SOURCES["umumiy"]["title"], "items": merged, "error": None}

    try:
        html = fetch_html(src["url"])
        blocks = extract_blocks_from_lex(html)
        items = find_matches_in_blocks(query, blocks, limit=10)
        return {
            "category": cat,
            "title": src["title"],
            "url": src["url"],
            "items": items,
            "error": None
        }
    except Exception as e:
        return {
            "category": cat,
            "title": src["title"],
            "url": src.get("url", ""),
            "items": [],
            "error": str(e)
        }

# ====== 3) UI (қора интерфейс + меню + Enter submit + Кирилл/Лотин) ======
PAGE = r"""
<!doctype html>
<html lang="uz">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>AL Юрист</title>
  <style>
    :root{
      --bg:#070b16; --panel:#0d1426; --panel2:#0b1222; --txt:#e8eefc; --muted:#a9b6d6;
      --line:#1e2a47; --accent:#4da3ff; --good:#43d18a; --bad:#ff5c6a;
      --shadow: 0 14px 40px rgba(0,0,0,.35);
      --radius:18px;
    }
    body{margin:0; font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial; background:radial-gradient(1200px 800px at 15% 10%, #0b1a37 0%, var(--bg) 45%, #050713 100%); color:var(--txt);}
    .wrap{max-width:1100px; margin:0 auto; padding:28px 16px 60px;}
    .top{display:flex; gap:14px; align-items:center; justify-content:space-between; margin-bottom:18px;}
    .brand{display:flex; flex-direction:column; gap:4px;}
    h1{margin:0; font-size:28px; letter-spacing:.2px;}
    .sub{color:var(--muted); font-size:13px;}
    .pill{background:rgba(77,163,255,.12); color:var(--txt); border:1px solid rgba(77,163,255,.25); padding:8px 10px; border-radius:999px; font-size:12px}
    .grid{display:grid; grid-template-columns: 1.1fr .9fr; gap:16px;}
    @media(max-width:980px){ .grid{grid-template-columns:1fr;} }

    .card{background:linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.015)); border:1px solid var(--line); border-radius:var(--radius); box-shadow:var(--shadow); }
    .card .hd{padding:14px 16px; border-bottom:1px solid rgba(30,42,71,.7); display:flex; align-items:center; justify-content:space-between;}
    .card .bd{padding:16px;}
    .tabs{display:flex; flex-wrap:wrap; gap:8px;}
    .tab{
      padding:8px 12px; border-radius:999px; border:1px solid var(--line); background:rgba(0,0,0,.15);
      color:var(--txt); cursor:pointer; font-size:13px;
    }
    .tab.active{background:rgba(77,163,255,.15); border-color:rgba(77,163,255,.35);}
    .modes{display:flex; gap:8px; margin-top:10px;}
    .mode{padding:7px 10px; border-radius:10px; border:1px solid var(--line); background:rgba(0,0,0,.12); cursor:pointer; color:var(--muted); font-size:13px;}
    .mode.active{color:var(--txt); border-color:rgba(77,163,255,.35); background:rgba(77,163,255,.12);}

    textarea{width:100%; min-height:140px; resize:vertical; border-radius:14px; border:1px solid var(--line); background:rgba(0,0,0,.25); color:var(--txt); padding:12px; font-size:14px; outline:none;}
    textarea:focus{border-color:rgba(77,163,255,.55); box-shadow:0 0 0 3px rgba(77,163,255,.12);}
    .row{display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin-top:12px;}
    button{
      border:0; cursor:pointer; padding:10px 14px; border-radius:12px; background:linear-gradient(180deg, rgba(77,163,255,.95), rgba(77,163,255,.75));
      color:#061027; font-weight:700;
    }
    .ghost{background:rgba(255,255,255,.06); color:var(--txt); border:1px solid var(--line); font-weight:600;}
    .hint{color:var(--muted); font-size:12px;}
    .chips{display:flex; flex-wrap:wrap; gap:8px; margin-top:10px;}
    .chip{background:rgba(255,255,255,.06); border:1px solid var(--line); color:var(--txt); padding:6px 10px; border-radius:999px; cursor:pointer; font-size:12px;}

    .results{display:flex; flex-direction:column; gap:10px;}
    .item{
      background:rgba(0,0,0,.18); border:1px solid rgba(30,42,71,.8); border-radius:14px; padding:12px 12px;
    }
    .item .t{display:flex; justify-content:space-between; gap:10px; align-items:flex-start;}
    .item .modda{font-weight:800;}
    .item a{color:var(--accent); text-decoration:none}
    .item a:hover{text-decoration:underline}
    .item .p{color:var(--muted); font-size:13px; margin-top:6px; line-height:1.35;}
    .small{font-size:12px; color:var(--muted);}
    .ok{color:var(--good); font-weight:700}
    .err{color:var(--bad); font-weight:700}
    .footerNote{margin-top:14px; font-size:12px; color:var(--muted);}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div class="brand">
        <h1>AL Юрист</h1>
        <div class="sub">Кодекс/қонун ичида “модда”ни қидиради (lex.uz очиқ манба) — HR буйруқ/қарор учун демо</div>
      </div>
      <div class="pill" id="enterHint">Enter босинг ✅</div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="hd">
          <div><b>Қидирув панели</b> <span class="small">— категория танланг</span></div>
          <div class="tabs" id="tabs"></div>
        </div>
        <div class="bd">
          <div class="modes">
            <div class="mode active" data-mode="keyword">Қидирув (калит сўз)</div>
            <div class="mode" data-mode="doc">Буйруқ/қарор матни (асос топиш)</div>
          </div>

          <div style="margin-top:12px;">
            <div class="small" id="labelText">Калит сўз (қисқа ёзинг):</div>
            <textarea id="q" placeholder="Масалан: ишдан бўшатиш, меҳнат шартномаси, интизомий жазо..."></textarea>

            <div class="row">
              <button id="btn">Қидириш</button>
              <button class="ghost" id="toggle">Кирилл ⇄ Лотин</button>
              <span class="hint">Shift+Enter — янги қатор. Enter — қидиради.</span>
            </div>

            <div class="chips" id="chips"></div>
            <div class="footerNote">
              Эслатма: бу демо. Натижа “асос” топишга ёрдам беради, расмий қарор/буйруқ олдидан матнни текшириб чиқинг.
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="hd">
          <div><b>Натижа</b></div>
          <div class="small" id="status">—</div>
        </div>
        <div class="bd">
          <div class="results" id="results"></div>
        </div>
      </div>
    </div>
  </div>

<script>
  const SOURCES = {{ sources_json | safe }};
  const DEFAULT_ORDER = {{ default_order | safe }};

  let currentCat = "mehnat";
  let mode = "keyword";
  let isCyr = true;

  const tabsEl = document.getElementById("tabs");
  const chipsEl = document.getElementById("chips");
  const qEl = document.getElementById("q");
  const resultsEl = document.getElementById("results");
  const statusEl = document.getElementById("status");
  const labelEl = document.getElementById("labelText");

  function buildTabs(){
    tabsEl.innerHTML = "";
    const items = [
      ["mehnat","Меҳнат кодекси"],
      ["umumiy","Қонун коддалар (умумий)"],
      ["mamuriy","Маъмурий жавобгарлик"],
      ["jinoyat","Жиноий жавобгарлик"],
      ["konstitutsiya","Конституция"],
      ["dfx","Давлат фуқаролик хизмати"],
      ["fuqarolik","Фуқаролик кодекси"],
    ];
    items.forEach(([key,label])=>{
      const b=document.createElement("div");
      b.className="tab"+(key===currentCat?" active":"");
      b.textContent=label;
      b.onclick=()=>{ currentCat=key; buildTabs(); setChips(); runSearch(); };
      tabsEl.appendChild(b);
    });
  }

  function setMode(newMode){
    mode = newMode;
    document.querySelectorAll(".mode").forEach(m=>{
      m.classList.toggle("active", m.dataset.mode===mode);
    });
    labelEl.textContent = mode==="keyword" ? "Калит сўз (қисқа ёзинг):" : "Буйруқ/қарор матнини тўлиқ ташланг:";
    qEl.placeholder = mode==="keyword"
      ? "Масалан: ишдан бўшатиш, меҳнат шартномаси, интизомий жазо..."
      : "Бу ерга буйруқ/қарор матнини қўйинг. Система калит сўзларни ўзи топиб, асослардан моддаларни чиқаради.";
    setChips();
  }

  function setChips(){
    chipsEl.innerHTML = "";
    const presets = {
      mehnat: ["ишдан бўшатиш","ишга қабул қилиш","меҳнат шартномаси","интизомий жазо","таътил","иш вақти"],
      mamuriy: ["маъмурий жавобгарлик","жарима","баённома","маъмурий ҳибс"],
      jinoyat: ["жиноят таркиби","жазо","жавобгарлик","квалификация"],
      konstitutsiya: ["ҳуқуқ ва эркинлик","давлат ҳокимияти","фуқаро","референдум"],
      dfx: ["танлов","давлат хизматчиси","28-модда","интизом"],
      fuqarolik: ["шартнома","даъво","мулк","мажбурият"],
      umumiy: ["ишдан бўшатиш","шартнома","жарима","жавобгарлик"]
    };
    (presets[currentCat]||presets["umumiy"]).forEach(t=>{
      const c=document.createElement("div");
      c.className="chip";
      c.textContent=t;
      c.onclick=()=>{ qEl.value=t; runSearch(); };
      chipsEl.appendChild(c);
    });
  }

  function escapeHtml(s){
    return (s||"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
  }

  async function runSearch(){
    const q = qEl.value.trim();
    if(!q){ resultsEl.innerHTML=""; statusEl.textContent="Калит сўз киритинг"; return; }
    statusEl.textContent="Қидирилмоқда...";
    resultsEl.innerHTML="";

    const res = await fetch("/api/search", {
      method:"POST",
      headers:{ "Content-Type":"application/json" },
      body: JSON.stringify({ cat: currentCat, q, mode })
    });
    const data = await res.json();

    if(data.error){
      statusEl.innerHTML = '<span class="err">Хато:</span> '+escapeHtml(data.error);
      return;
    }

    // Умумий режимда бир нечта категория қайтиши мумкин
    if(data.category==="umumiy"){
      let total = 0;
      data.items.forEach(group=> total += (group.items||[]).length );
      statusEl.innerHTML = `<span class="ok">Топилди:</span> ${total} та натижа`;
      data.items.forEach(group=>{
        const h = document.createElement("div");
        h.className="small";
        h.style.margin="10px 0 6px";
        h.innerHTML = `<b>${escapeHtml(group.title)}</b> — <a href="${group.url}" target="_blank" rel="noopener">lex.uz</a>`;
        resultsEl.appendChild(h);
        (group.items||[]).forEach(it=> addItem(group, it));
      });
      if(total===0){
        resultsEl.innerHTML = '<div class="small">Натижа топилмади. Калит сўзни бошқача ёзинг (масалан: “бўшатиш”, “шартнома”, “интизом”).</div>';
      }
      return;
    }

    statusEl.innerHTML = `<span class="ok">Топилди:</span> ${(data.items||[]).length} та натижа`;
    (data.items||[]).forEach(it=> addItem(data, it));
    if((data.items||[]).length===0){
      resultsEl.innerHTML = '<div class="small">Натижа топилмади. Калит сўзни қисқартиринг ёки бошқача синоним қилинг.</div>';
    }
  }

  function addItem(group, it){
    const d=document.createElement("div");
    d.className="item";
    d.innerHTML = `
      <div class="t">
        <div class="modda">${escapeHtml(it.modda || "")}</div>
        <div class="small"><a href="${group.url}" target="_blank" rel="noopener">Манба: lex.uz</a></div>
      </div>
      <div class="p">${escapeHtml(it.preview || "")}</div>
    `;
    resultsEl.appendChild(d);
  }

  // Кирилл ⇄ Лотин (оддий транслит)
  const map = [
    ["sh","ш"],["ch","ч"],["ng","нг"],["yo","ё"],["yu","ю"],["ya","я"],["o'","ў"],["g'","ғ"],
    ["a","а"],["b","б"],["d","д"],["e","е"],["f","ф"],["g","г"],["h","ҳ"],["i","и"],["j","ж"],["k","к"],
    ["l","л"],["m","м"],["n","н"],["o","о"],["p","п"],["q","қ"],["r","р"],["s","с"],["t","т"],["u","у"],
    ["v","в"],["x","х"],["y","й"],["z","з"]
  ];

  function toCyr(text){
    let s=text;
    // аввал махсус икки ҳарфлилар
    const pairs = [["g'","ғ"],["o'","ў"],["sh","ш"],["ch","ч"],["ng","нг"],["yo","ё"],["yu","ю"],["ya","я"]];
    pairs.forEach(([a,b])=>{
      s = s.replaceAll(a.toLowerCase(), b).replaceAll(a.toUpperCase(), b.toUpperCase());
    });
    // қолган ҳарфлар
    map.forEach(([a,b])=>{
      s = s.replaceAll(a, b);
      s = s.replaceAll(a.toUpperCase(), b.toUpperCase());
    });
    return s;
  }

  function toLat(text){
    // минимал қайтариш (демо): кирилл -> лотин
    const back = [
      ["ғ","g'"],["ў","o'"],["ш","sh"],["ч","ch"],["нг","ng"],["ё","yo"],["ю","yu"],["я","ya"],
      ["ҳ","h"],["қ","q"],["х","x"],["ж","j"],
      ["а","a"],["б","b"],["д","d"],["е","e"],["ф","f"],["г","g"],["и","i"],["к","k"],["л","l"],["м","m"],
      ["н","n"],["о","o"],["п","p"],["р","r"],["с","s"],["т","t"],["у","u"],["в","v"],["й","y"],["з","z"]
    ];
    let s=text;
    back.forEach(([c,l])=>{
      s = s.replaceAll(c, l);
      s = s.replaceAll(c.toUpperCase(), l.charAt(0).toUpperCase()+l.slice(1));
    });
    return s;
  }

  document.getElementById("btn").onclick = runSearch;
  document.getElementById("toggle").onclick = ()=>{
    const v = qEl.value;
    qEl.value = isCyr ? toLat(v) : toCyr(v);
    isCyr = !isCyr;
  };

  // Enter босилса қидиради (Shift+Enter бўлса янги қатор)
  qEl.addEventListener("keydown", (e)=>{
    if(e.key==="Enter" && !e.shiftKey){
      e.preventDefault();
      runSearch();
    }
  });

  // Mode тугмалари
  document.querySelectorAll(".mode").forEach(m=>{
    m.onclick = ()=> setMode(m.dataset.mode);
  });

  // init
  buildTabs();
  setChips();
</script>
</body>
</html>
"""

@app.get("/")
def index():
    return render_template_string(
        PAGE,
        sources_json=SOURCES,
        default_order=DEFAULT_ORDER
    )

@app.post("/api/search")
def api_search():
    data = request.get_json(force=True) or {}
    cat = (data.get("cat") or "mehnat").strip()
    q = (data.get("q") or "").strip()
    mode = (data.get("mode") or "keyword").strip()

    if not q:
        return jsonify({"error": "empty query"}), 400

    # 1) Агар “Буйруқ/қарор матни” режими бўлса — калит сўзларни ўзи топади
    if mode == "doc":
        keywords = extract_keywords_from_text(q, max_keywords=6)
        if not keywords:
            return jsonify({"error": "Матндан калит сўз чиқмади. Қисқароқ ва аниқ сўзлар билан қайта урининг."})

        # Биринчи калит сўз билан қидириб, натижа бўлмаса кейингига ўтади
        agg = []
        for kw in keywords:
            r = search_one_source(cat, kw)
            # Умумий бўлса — структураси бошқача
            if r.get("category") == "umumiy":
                # агар бирорта натижа чиқса — шуни қайтарамиз
                has_any = any((g.get("items") for g in r.get("items", [])))
                if has_any:
                    r["used_keywords"] = keywords
                    return jsonify(r)
            else:
                if r.get("items"):
                    r["used_keywords"] = keywords
                    return jsonify(r)
            agg.append({"kw": kw, "found": 0})

        # Ҳеч нарса топилмади
        return jsonify({
            "category": cat,
            "title": SOURCES.get(cat, {}).get("title", cat),
            "items": [],
            "used_keywords": keywords,
            "error": None
        })

    # 2) Оддий калит сўз режими
    result = search_one_source(cat, q)
    return jsonify(result)

if __name__ == "__main__":
    # локал ишлатиш учун
    app.run(host="0.0.0.0", port=5000, debug=True)
