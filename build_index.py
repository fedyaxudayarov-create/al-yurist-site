# build_index.py
import os
import re
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "lex_index.db"

# filename -> (code_key, code_title)
CODE_FILES = {
    "mehnat_kodeksi.txt": ("mehnat", "Меҳнат кодекси"),
    "jinoyat_kodeksi.txt": ("jinoyat", "Жиноят кодекси"),
    "mamuriy_kodeks.txt": ("mamuriy", "Маъмурий жавобгарлик тўғрисидаги кодекс"),
    "konstitutsiya.txt": ("konstitutsiya", "Конституция"),
    "davlat_xizmati.txt": ("davlat", "Давлат фуқаролик хизмати тўғрисидаги қонун"),
    "mahalliy_hokimiyat.txt": ("mahalliy", "Маҳаллий давлат ҳокимияти тўғрисидаги қонун"),
}

# Модда сарлавҳасини ушлайди:
# 1-модда. ...
# 1 - модда ...
# Модда 1. ...
ARTICLE_PATTERNS = [
    re.compile(r"(?mi)^\s*(\d+)\s*[-–—]?\s*(модда|modda)\.?\s*(.*)$"),
    re.compile(r"(?mi)^\s*(модда|modda)\s*(\d+)\.?\s*(.*)$"),
]

def read_text(p: Path) -> str:
    # TXT’лар турли кодировкада бўлиши мумкин
    for enc in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            return p.read_text(encoding=enc)
        except Exception:
            pass
    # охирги чора
    return p.read_text(encoding="utf-8", errors="ignore")

def split_articles(full_text: str):
    """
    Қайтаради: list of dicts:
    {article_no, title, text}
    """
    text = full_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    # Энг биринчи паттерн билан топиб кўрамиз, топилмаса иккинчиси
    matches = []
    used_pat = None
    for pat in ARTICLE_PATTERNS:
        ms = list(pat.finditer(text))
        if len(ms) >= 2:  # камида 2 та модда бўлса, парслаш осон
            matches = ms
            used_pat = pat
            break

    # Агар модда сарлавҳалари топилмаса — йирик парча қилиб қўямиз
    if not matches:
        chunks = []
        step = 1800
        for i in range(0, len(text), step):
            part = text[i:i+step].strip()
            if part:
                chunks.append({
                    "article_no": "",
                    "title": "Матн бўлими",
                    "text": part
                })
        return chunks

    items = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        block = text[start:end].strip()

        g = m.groups()

        # Иккита форматни нормаллаштирамиз
        # Pattern1: (\d+) (модда) (title)
        # Pattern2: (модда) (\d+) (title)
        if used_pat is ARTICLE_PATTERNS[0]:
            article_no = g[0].strip()
            title_tail = (g[2] or "").strip()
        else:
            article_no = g[1].strip()
            title_tail = (g[2] or "").strip()

        # Биринчи қаторда “1-модда. ...” сарлавҳа бўлади — уни тоза қилиб оламиз
        # Блокни тозалаш: биринчи қаторни қолдирамиз, лекин матнда ҳам бўлсин десангиз қолдириш мумкин.
        # Биз матнда сақлаб қўямиз, лекин title алоҳида.
        title = title_tail if title_tail else f"{article_no}-модда"

        items.append({
            "article_no": article_no,
            "title": title,
            "text": block
        })

    return items

def init_db(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("DROP TABLE IF EXISTS items;")
    cur.execute("DROP TABLE IF EXISTS items_fts;")

    cur.execute("""
    CREATE TABLE items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code_key TEXT NOT NULL,
        code_title TEXT NOT NULL,
        article_no TEXT,
        title TEXT,
        text TEXT NOT NULL,
        url TEXT
    );
    """)

    # FTS5: қидириш учун
    cur.execute("""
    CREATE VIRTUAL TABLE items_fts USING fts5(
        code_title,
        article_no,
        title,
        text,
        tokenize = 'unicode61'
    );
    """)

    cur.execute("CREATE INDEX idx_items_code_key ON items(code_key);")
    conn.commit()

def add_item(conn: sqlite3.Connection, code_key, code_title, article_no, title, text, url):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO items(code_key, code_title, article_no, title, text, url) VALUES(?,?,?,?,?,?)",
        (code_key, code_title, article_no, title, text, url)
    )
    rowid = cur.lastrowid
    cur.execute(
        "INSERT INTO items_fts(rowid, code_title, article_no, title, text) VALUES(?,?,?,?,?)",
        (rowid, code_title, article_no, title, text)
    )
    return rowid

def build():
    if not DATA_DIR.exists():
        raise RuntimeError(f"data/ папка топилмади: {DATA_DIR}")

    # DB файлни тозалаймиз
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    init_db(conn)

    total = 0
    per_code = {}

    for fname, (code_key, code_title) in CODE_FILES.items():
        p = DATA_DIR / fname
        if not p.exists():
            print(f"[SKIP] {fname} топилмади (data/ ичига қўйинг).")
            continue

        full_text = read_text(p)
        articles = split_articles(full_text)

        cnt = 0
        for a in articles:
            article_no = a.get("article_no", "") or ""
            title = a.get("title", "") or ""
            text = a.get("text", "") or ""
            if not text.strip():
                continue

            # UI’да босилганда ишламай қолмасин десак: #... қиламиз
            url = f"#:{code_key}:{article_no or cnt+1}"

            add_item(conn, code_key, code_title, article_no, title, text, url)
            cnt += 1

        per_code[code_key] = cnt
        total += cnt
        print(f"[OK] {fname} -> {code_key}: {cnt} та бўлим/модда")

    conn.commit()
    conn.close()

    print("\n======== DONE ========")
    print(f"DB: {DB_PATH}")
    print(f"TOTAL ITEMS: {total}")
    for k, v in per_code.items():
        print(f" - {k}: {v}")

if __name__ == "__main__":
    build()
