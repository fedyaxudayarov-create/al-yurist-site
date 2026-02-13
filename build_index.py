# build_index.py
import re
import sqlite3
from pathlib import Path

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "lex_index.db"


# app.py dagi категориялар билан мослаштириш
KNOWN_KEYS = {
    "mehnat": "Меҳнат кодекси",
    "jinoyat": "Жиноий жавобгарлик (ЖК)",
    "mamuriy": "Маъмурий жавобгарлик (МЖтК)",
    "konstitutsiya": "Конституция",
    "fuqarolik": "Фуқаролик кодекси",
    "davlat_xizmati": "Давлат фуқаролик хизмати",
    "umumiy": "Қонун-қоидалар (умумий)",
    # агар сиз янги файл қўшган бўлсангиз:
    "mahalliy_hokimiyat": "Маҳаллий давлат ҳокимияти",
}

def detect_code_key(stem: str) -> str:
    s = stem.lower()

    # файл номидан тахмин қиламиз
    if "mehnat" in s:
        return "mehnat"
    if "jinoyat" in s:
        return "jinoyat"
    if "mamuriy" in s:
        return "mamuriy"
    if "konstitutsiya" in s:
        return "konstitutsiya"
    if "fuqarolik" in s:
        return "fuqarolik"
    if "davlat" in s and "xizmat" in s:
        return "davlat_xizmati"
    if "mahalliy" in s and "hokim" in s:
        # app.py да бу кнопка йўқ, лекин қидиришда ишлайди (кейин истасангиз app.py га кнопка қўшамиз)
        return "mahalliy_hokimiyat"

    return "umumiy"

def read_text_safely(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    # охирги чора: хатоларни алмаштириб ўқиймиз
    return raw.decode("utf-8", errors="replace")

def parse_articles(text: str):
    """
    Матндан моддаларни ажратиш.
    Қўллаб-қувватлайди:
      - "14-модда"
      - "14 - модда"
      - "14-модда. Сарлавҳа"
      - "Модда 14. ..."
    Агар топилмаса — бутун файл 1 та ёзув бўлиб киритилади.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    # модда бошланишига ўхшаш қаторлар
    # (катта/кичик, кирилл/лотин аралаш ҳолатлар учун йенгилроқ regex)
    pat = re.compile(
        r"^\s*(?:Модда\s+(\d+)|(\d+)\s*[-–]?\s*модда)\b[^\S\r\n]*(.*)$",
        re.IGNORECASE,
    )

    hits = []
    for idx, line in enumerate(lines):
        m = pat.match(line)
        if m:
            no = m.group(1) or m.group(2)
            tail = (m.group(3) or "").strip(" .-–\t")
            hits.append((idx, no, tail))

    if not hits:
        # модда топилмаса — 1 та “мақола” қилиб киритамиз
        whole = text.strip()
        if not whole:
            return []
        return [("0", "", whole)]

    items = []
    for i, (start_line, no, tail) in enumerate(hits):
        end_line = hits[i + 1][0] if i + 1 < len(hits) else len(lines)
        body = "\n".join(lines[start_line:end_line]).strip()
        if not body:
            continue

        article_no = str(no).strip()
        article_title = tail.strip()[:200]  # жуда узун бўлмасин
        items.append((article_no, article_title, body))

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
            article_title TEXT,
            text TEXT NOT NULL,
            url TEXT
        );
    """)

    # FTS5: snippet(items_fts, 1, ...) app.py да 1-устун = text бўлиши керак
    cur.execute("""
        CREATE VIRTUAL TABLE items_fts USING fts5(
            title,
            text
        );
    """)

    conn.commit()

def main():
    if not DATA_DIR.exists():
        raise SystemExit(f"data папка топилмади: {DATA_DIR}")

    txt_files = sorted(DATA_DIR.glob("*.txt"))
    if not txt_files:
        raise SystemExit("data папкада .txt файллар топилмади. Аввал .txt файлларни data/ га қўйинг.")

    # базани қайтадан ясаймиз
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    init_db(conn)
    cur = conn.cursor()

    total_articles = 0
    total_files = 0

    for fp in txt_files:
        code_key = detect_code_key(fp.stem)
        code_title = KNOWN_KEYS.get(code_key, "Қонун-қоидалар (умумий)")

        text = read_text_safely(fp).strip()
        if not text:
            continue

        articles = parse_articles(text)
        if not articles:
            continue

        total_files += 1

        for article_no, article_title, body in articles:
            # title: модда сарлавҳаси бўлмаса ҳам, камида “<код> <модда>” қилиб қўямиз
            fts_title = f"{code_title}"
            if article_no:
                fts_title += f" — {article_no}-модда"
            if article_title:
                fts_title += f": {article_title}"

            url = None  # кейин хоҳласангиз lex.uz линкларини ҳам тиқиш мумкин

            cur.execute(
                "INSERT INTO items(code_key, code_title, article_no, article_title, text, url) VALUES (?,?,?,?,?,?)",
                (code_key, code_title, article_no, article_title, body, url),
            )
            new_id = cur.lastrowid

            cur.execute(
                "INSERT INTO items_fts(rowid, title, text) VALUES (?,?,?)",
                (new_id, fts_title, body),
            )
            total_articles += 1

    conn.commit()
    conn.close()

    print(f"OK: База тайёр: {DB_PATH}")
    print(f"OK: Файллар: {total_files} та, ёзувлар (модда/бўлим): {total_articles} та")

if __name__ == "__main__":
    main()
