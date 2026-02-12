import os, re, json
from datetime import datetime

DATA_DIR = "data"
OUT_PATH = os.path.join(DATA_DIR, "index.json")

def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\s‘’ʼ'-]", " ", s, flags=re.U)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def split_into_articles(text: str):
    """
    Оддий, лекин ишончли усул:
    'Модда 1.' / '1-модда' / '1. ' каби сарлавҳаларни ушлаб, блокларга бўлади.
    """
    t = text.replace("\r", "")
    # турли ёзилишларни қўллаб-қувватлаш
    pattern = re.compile(
        r"(?P<h>(?:\n|^)\s*(?:\d+\s*[-–]?\s*модда|\bмодда\s*\d+|\d+\.)\s*.*)",
        re.IGNORECASE
    )

    hits = list(pattern.finditer(t))
    if not hits:
        # Агар моддага бўлинмаса — бутун матнни 1та ҳужжат қиламиз
        return [{"article_no": None, "title": "Матн", "body": t.strip()}]

    blocks = []
    for i, m in enumerate(hits):
        start = m.start()
        end = hits[i+1].start() if i+1 < len(hits) else len(t)
        block = t[start:end].strip()

        first_line = block.split("\n", 1)[0].strip()
        body = block[len(first_line):].strip()

        # article рақамини топиш
        num = None
        mnum = re.search(r"(\d+)", first_line)
        if mnum:
            num = int(mnum.group(1))

        blocks.append({
            "article_no": num,
            "title": first_line,
            "body": body if body else block
        })
    return blocks

def build():
    os.makedirs(DATA_DIR, exist_ok=True)

    sources = [
        # кейин бошқаларни қўшасиз
        ("mehnat", "Меҳнат кодекси", os.path.join(DATA_DIR, "mehnat_kodeksi.txt")),
    ]

    items = []
    for cat, doc_name, path in sources:
        if not os.path.exists(path):
            print(f"[SKIP] Not found: {path}")
            continue

        text = read_text(path)
        articles = split_into_articles(text)

        for a in articles:
            body = a["body"].strip()
            if len(body) < 50:
                continue

            item = {
                "id": f"{cat}-{a['article_no'] or 'x'}-{len(items)}",
                "category": cat,
                "doc_name": doc_name,
                "article_no": a["article_no"],
                "title": a["title"],
                "text": body,
                "text_norm": normalize(a["title"] + " " + body),
                "source": path,
            }
            items.append(item)

    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(items),
        "items": items
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[OK] Wrote {OUT_PATH} with {len(items)} items")

if __name__ == "__main__":
    build()
