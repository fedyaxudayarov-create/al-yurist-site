import os
import re
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "lex_index.db"

# code_key -> инсонга кўринадиган номи (сизда app.py'даги CATEGORIES билан мос)
CODE_TITLES = {
    "mehnat": "Меҳнат кодекси",
    "jinoyat": "Жиноий жавобгарлик (ЖК)",
    "mamuriy": "Маъмурий жавобгарлик (МЖтК)",
    "konstit": "Конституция",
    "davlat_xizmati": "Давлат фуқаролик хизмати",
    "mahalliy_hokimiyat": "Маҳаллий давлат ҳокимияти",
}

# code_key -> data'даги файл номи
CODE_FILES = {
    "mehnat": "mehnat_kodeksi.txt",
    "jinoyat": "jinoyat_kodeksi.txt",
    "mamuriy": "mamuriy_kodeks.txt",
    "konstit": "konstitutsiya.txt",
    "davlat_xizmati": "davlat_xizmati.txt",
    "mahalliy_hokimiyat": "mahalliy_hokimiyat.txt",
}
MODDA_RE = re.compile(
    r"(?im)^\s*(?:(\d{1,4})\s*[-–—]?\s*модда|модда\s*(\d{1,4}))\.?\b\s*(.*)$"
)

def read_text_file(path: Path) -> str:
    # txt файллар кирилл/латин аралаш бўлиши мумкин — шунга мос
    return path.read_text(encoding="utf-8", errors="ignore")

def split_into_articles(text: str):
    """
    Матнни "N-модда" сарлавҳалари бўйича бўлади.
    Қайтаради: [(article_no, title_line, body_text), ...]
    """
    lines = text.splitlines()
    hits = []
    for i, line in enumerate(lines):
        m = ARTICLE_RE.match(line)
        if m:
            hits.append((i, m.group(1), line.strip()))

    # агар модда топилмаса — битта "умумий" мақола қилиб қайтар
    if not hits:
        cleaned = text.strip()
        if not cleaned:
            return []
        return [("", "", cleaned)]

    out = []
    for idx, (line_i, no, title_line) in enumerate(hits):
        start = line_i
        end = hits[idx + 1][0] if idx + 1 < len(hits) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        # title_line — биринчи сатр (масалан: "14-модда. ...")
        out.append((no, title_line, body))
    return out

def init_db(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")

    # асосий жадвал
    cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code_key TEXT NOT NULL,
            code_title TEXT NOT NULL,
            article_no TEXT,
            title TEXT,
            text TEXT NOT NULL,
            url TEXT
        );
    """)

    # FTS (қидирув) жадвали — rowid = items.id бўлади
    cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS items_fts
        USING fts5(
            text,
            title,
            code_key,
            tokenize='unicode61'
        );
    """)

    # қайта индексация учун тозалаш
    cur.execute("DELETE FROM items;")
    cur.execute("DELETE FROM items_fts;")

    conn.commit()

def insert_item(conn: sqlite3.Connection, code_key: str, code_title: str,
                article_no: str, title: str, body: str, url: str = ""):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO items(code_key, code_title, article_no, title, text, url) VALUES (?,?,?,?,?,?)",
        (code_key, code_title, article_no or "", title or "", body, url or "")
    )
    rowid = cur.lastrowid
    cur.execute(
        "INSERT INTO items_fts(rowid, text, title, code_key) VALUES (?,?,?,?)",
        (rowid, body, title or "", code_key)
    )

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    try:
        init_db(conn)

        total_files = 0
        total_items = 0

        for code_key, fname in CODE_FILES.items():
            path = DATA_DIR / fname
            if not path.exists():
                print(f"SKIP: {fname} topilmadi (data/ ichida yo‘q)")
                continue

            code_title = CODE_TITLES.get(code_key, code_key)
            text = read_text_file(path).strip()
            if not text:
                print(f"SKIP: {fname} bo‘sh")
                continue

            parts = split_into_articles(text)
            if not parts:
                print(f"SKIP: {fname} (modda ham topilmadi, matn ham yo‘q)")
                continue

            for article_no, title_line, body in parts:
                # url ҳозирча бўш — кейин хохласанг lex.uz линк қўшамиз
                insert_item(conn, code_key, code_title, article_no, title_line, body, url="")
                total_items += 1

            total_files += 1

        conn.commit()
        print(f"OK: lex_index.db tayyor. Fayl: {total_files} ta, yozuv: {total_items} ta")
        print(f"DB PATH: {DB_PATH}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
