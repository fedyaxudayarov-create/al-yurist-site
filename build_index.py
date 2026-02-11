import re
import json
import time
import sqlite3
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DB_PATH = Path("data/lex_index.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ⚠️ МАНА ШУ ЕРГА lex.uz /docs/ID ларни қўясиз
CODES = {
    "mehnat": {
        "title": "Меҳнат кодекси",
        "doc_id": 0,  # <-- бу ерга рақам қўйинг
    },
    "jinoyat": {
        "title": "Жиноят кодекси",
        "doc_id": 0,
    },
    "mamuriy": {
        "title": "Маъмурий жавобгарлик тўғрисидаги кодекс",
        "doc_id": 0,
    },
    "konstitutsiya": {
        "title": "Конституция",
        "doc_id": 0,
    },
    "fuqarolik": {
        "title": "Фуқаролик кодекси",
        "doc_id": 0,
    },
    "davlat_xizmati": {
        "title": "«Давлат фуқаролик хизмати тўғрисида» Қонун",
        "doc_id": 0,
    },
}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"

def fetch_doc_html(doc_id: int) -> str:
    url = f"https://lex.uz/docs/{doc_id}"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.text

def clean_text(t: str) -> str:
    t = re.sub(r"\s+", " ", t)
    return t.strip()

def guess_article_blocks(soup: BeautifulSoup):
    """
    lex.uz html турлича бўлиши мумкин.
    Биз умумий усул қиламиз: катта текст контейнердаги p/li/div бўлакларни йиғамиз,
    кейин "Модда" / "Article" каби сарлавҳаларни топиб ажратамиз.
    """
    # Энг катта матн чиқадиган контейнерни топишга ҳаракат
    main = soup.find("main") or soup.find("article") or soup.body
    if not main:
        return []

    text_nodes = []
    for tag in main.find_all(["h1", "h2", "h3", "p", "li", "div"], recursive=True):
        txt = tag.get_text(" ", strip=True)
        if not txt:
            continue
        # жуда майда меню/тугма матнларини ташлаб кетамиз
        if len(txt) < 25:
            continue
        text_nodes.append(txt)

    full = "\n".join(text_nodes)

    # "Модда" бўйича бўлиш (кирил/лотин вариантларга ҳам тайёр туриш)
    pattern = re.compile(r"(?:(?:\n|^)\s*)(Модда\s*\d+[^ \n]*.*|Modda\s*\d+[^ \n]*.*)", re.IGNORECASE)
    matches = list(pattern.finditer(full))

    if not matches:
        # агар модда топилмаса — бутун матнни битта блок қиламиз (кам бўлса ҳам ишлайди)
        return [{"article_no": "", "title": "Бутун ҳужжат", "text": clean_text(full)}]

    blocks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i+1].start() if i+1 < len(matches) else len(full)
        head = clean_text(m.group(1))
        body = clean_text(full[m.end():end])

        # сарлавҳа/номерни ажратиб олиш
        no_match = re.search(r"(\d+)", head)
        article_no = no_match.group(1) if no_match else ""
        blocks.append({
            "article_no": article_no,
            "title": head,
            "text": f"{head}. {body}".strip()
        })

    # жуда қисқа блокларни фильтрлаймиз
    blocks = [b for b in blocks if len(b["text"]) > 80]
    return blocks

def init_db(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code_key TEXT NOT NULL,
        code_title TEXT NOT NULL,
        doc_id INTEGER NOT NULL,
        article_no TEXT,
        title TEXT,
        text TEXT NOT NULL,
        url TEXT NOT NULL
    );
    """)

    # FTS5 (тез қидириш)
    cur.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
        code_key, code_title, article_no, title, text, url,
        content='items', content_rowid='id'
    );
    """)
    conn.commit()

def rebuild_index(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("DELETE FROM items;")
    cur.execute("DELETE FROM items_fts;")
    conn.commit()

    for code_key, cfg in CODES.items():
        doc_id = int(cfg.get("doc_id", 0) or 0)
        if doc_id <= 0:
            print(f"[SKIP] {code_key}: doc_id қўйилмаган")
            continue

        print(f"[FETCH] {cfg['title']} (docs/{doc_id})")
        html = fetch_doc_html(doc_id)
        soup = BeautifulSoup(html, "lxml")

        blocks = guess_article_blocks(soup)
        url = f"https://lex.uz/docs/{doc_id}"

        for b in blocks:
            cur.execute("""
                INSERT INTO items(code_key, code_title, doc_id, article_no, title, text, url)
                VALUES(?,?,?,?,?,?,?)
            """, (code_key, cfg["title"], doc_id, b.get("article_no",""), b.get("title",""), b["text"], url))

        conn.commit()
        # lex.uz’га юк туширмаслик учун озgina танаффус
        time.sleep(1.2)

    # FTS’ни тўлдириш
    cur.execute("INSERT INTO items_fts(rowid, code_key, code_title, article_no, title, text, url) "
                "SELECT id, code_key, code_title, article_no, title, text, url FROM items;")
    conn.commit()
    print("[OK] Индекс тайёр!")

def main():
    print("DB:", DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    try:
        init_db(conn)
        rebuild_index(conn)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
