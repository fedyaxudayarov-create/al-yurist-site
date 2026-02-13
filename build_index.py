# build_index.py
import re
import sqlite3
from pathlib import Path

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "lex_index.db"

# файл номи -> категория
MAP = {
    "mehnat_kodeksi": "mehnat",
    "jinoyat_kodeksi": "jinoyat",
    "mamuriy_kodeks": "mamuriy", # Сиздаги файл номига мосланди
    "konstitutsiya": "konstitutsiya",
    "davlat_xizmati": "davlat_xizmati",
    "fuqarolik_kodeksi": "fuqarolik",
    "mahalliy_hokimiyat": "mamuriy" # Буни ҳам қўшиб қўйдик
}
ARTICLE_RE = re.compile(r"(?mi)^(?:Модда|Modda|Статья|Article)\s+(\d+)\s*[\.\-–:]?\s*(.*)$")

def detect_code_key(stem: str) -> str:
    return MAP.get(stem, "umumiy")

def split_articles(text: str):
    text = text.replace("\r\n", "\n")
    matches = list(ARTICLE_RE.finditer(text))
    if not matches:
        return [("", "", text.strip())]

    parts = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        article_no = m.group(1).strip()
        title = (m.group(2) or "").strip()
        body = text[m.end():end].strip()
        # сарлавҳа + матнни бирга сақлаймиз
        full_text = f"{m.group(0).strip()}\n{body}".strip()
        parts.append((article_no, title, full_text))
    return parts

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

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

    cur.execute("""
        CREATE VIRTUAL TABLE items_fts USING fts5(
            text,
            content='items',
            content_rowid='id',
            tokenize='unicode61'
        );
    """)

    cur.execute("""
        CREATE TRIGGER items_ai AFTER INSERT ON items BEGIN
            INSERT INTO items_fts(rowid, text) VALUES (new.id, new.text);
        END;
    """)
    cur.execute("""
        CREATE TRIGGER items_ad AFTER DELETE ON items BEGIN
            INSERT INTO items_fts(items_fts, rowid, text) VALUES('delete', old.id, old.text);
        END;
    """)
    cur.execute("""
        CREATE TRIGGER items_au AFTER UPDATE ON items BEGIN
            INSERT INTO items_fts(items_fts, rowid, text) VALUES('delete', old.id, old.text);
            INSERT INTO items_fts(rowid, text) VALUES (new.id, new.text);
        END;
    """)

    # code_title – интерфейсда чиқиши учун
    code_titles = {
        "mehnat": "Меҳнат кодекси",
        "jinoyat": "Жиноий жавобгарлик (ЖК)",
        "mamuriy": "Маъмурий жавобгарлик (МЖтК)",
        "konstitutsiya": "Конституция",
        "fuqarolik": "Фуқаролик кодекси",
        "davlat_xizmati": "Давлат фуқаролик хизмати",
        "umumiy": "Қонун-қоидалар (умумий)",
    }

    added = 0
    for path in sorted(DATA_DIR.glob("*.txt")):
        stem = path.stem
        code_key = detect_code_key(stem)
        code_title = code_titles.get(code_key, code_key)

        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            continue

        for article_no, title, full_text in split_articles(text):
            cur.execute(
                "INSERT INTO items(code_key, code_title, article_no, title, text, url) VALUES(?,?,?,?,?,?)",
                (code_key, code_title, article_no or None, title or None, full_text, "")
            )
            added += 1

    conn.commit()
    conn.close()
    print(f"✅ Индекс тайёр: {added} та модда/бўлим қўшилди. Файл: {DB_PATH}")

if __name__ == "__main__":
    main()
