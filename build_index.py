# build_index.py
# -*- coding: utf-8 -*-

import os
import re
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "lex_index.db"

# Файл номи -> (code_key, code_title)
CODE_MAP = {
    "mehnat_kodeksi": ("mehnat", "Меҳнат кодекси"),
    "jinoyat_kodeksi": ("jinoyat", "Жиноят кодекси"),
    "mamuriy_kodeks": ("mamuriy", "Маъмурий жавобгарлик тўғрисидаги кодекс"),
    "konstitusiya": ("konstitusiya", "Конституция"),
    "davlat_xizmati": ("davlat", "Давлат фуқаролик хизмати"),
    "mahalliy_hokimiyat": ("mahalliy", "Маҳаллий давлат ҳокимияти тўғрисидаги Қонун"),
}

# "14-модда", "14 модда", "14 - модда" (кирилл/лотин аралаш) ни ушлаш
ARTICLE_RE = re.compile(
    r"^\s*(\d{1,4})\s*[-–—]?\s*модда\b.*$",
    re.IGNORECASE
)

def normalize_text(s: str) -> str:
    s = s.replace("\ufeff", "").replace("\r", "")
    # ортиқча бўшлиқларни йиғамиз
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()

def split_into_articles(full_text: str):
    """
    Кўпинча кодекслар 'XX-модда' билан келади.
    Шу бўйича бўлиб, ҳар бир моддани алоҳида item қиламиз.
    Топилмаса — бутун файлни битта item қиламиз.
    """
    lines = [ln.strip() for ln in full_text.split("\n")]
    items = []
    cur_no = None
    cur_title = None
    cur_buf = []

    def flush():
        nonlocal cur_no, cur_title, cur_buf
        if cur_no is None:
            return
        text = "\n".join([x for x in cur_buf if x.strip()])
        items.append((cur_no, cur_title or f"{cur_no}-модда", text.strip()))
        cur_no = None
        cur_title = None
        cur_buf = []

    for ln in lines:
        m = ARTICLE_RE.match(ln)
        if m:
            flush()
            cur_no = m.group(1)
            # Сарлавҳа: шу сатрининг ўзи (одатда сарлавҳа шу ерда)
            cur_title = ln.strip()
            cur_buf = []
        else:
            if cur_no is not None:
                cur_buf.append(ln)

    flush()

    if not items:
        # modda топилмаса
        text = "\n".join([x for x in lines if x.strip()])
        return [("0", "Матн", text.strip())]

    return items

def ensure_schema(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code_key TEXT,
            code_title TEXT,
            article_no TEXT,
            title TEXT,
            text TEXT,
            url TEXT
        )
    """)
    # FTS5 (sqlite билан бирга келади, Render’da ҳам одатда бор)
    cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS items_fts
        USING fts5(title, text, content='items', content_rowid='id')
    """)
    conn.commit()

def main():
    if not DATA_DIR.exists():
        raise SystemExit(f"data папка топилмади: {DATA_DIR}")

    # Эски DB ни ўчириш
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))
    try:
        ensure_schema(conn)
        cur = conn.cursor()

        txt_files = sorted([p for p in DATA_DIR.glob("*.txt") if p.is_file()])
        files_used = 0
        total_items = 0

        for fp in txt_files:
            stem = fp.stem.lower()
            code_key, code_title = CODE_MAP.get(stem, (stem, stem))

            raw = fp.read_text(encoding="utf-8", errors="ignore")
            raw = normalize_text(raw)

            articles = split_into_articles(raw)

            for article_no, title, text in articles:
                if not text:
                    continue
                cur.execute(
                    "INSERT INTO items(code_key, code_title, article_no, title, text, url) VALUES (?,?,?,?,?,?)",
                    (code_key, code_title, str(article_no), title, text, "")
                )
                rowid = cur.lastrowid
                cur.execute(
                    "INSERT INTO items_fts(rowid, title, text) VALUES (?,?,?)",
                    (rowid, title, text)
                )
                total_items += 1

            files_used += 1

        conn.commit()

        print(f"Index ready: {files_used} files, {total_items} items")
        print(f"DB path: {DB_PATH}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
