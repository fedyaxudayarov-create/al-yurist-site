import os
import json
import re

DATA_DIR = "data"
OUT_FILE = "data/index.json"

def normalize(text):
    text = text.lower()
    text = re.sub(r"[^a-zа-яё0-9ўқғҳ\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

index = []

for fname in os.listdir(DATA_DIR):
    if not fname.endswith(".txt"):
        continue

    path = os.path.join(DATA_DIR, fname)
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    clean = normalize(text)

    index.append({
        "file": fname,
        "text": clean,
        "raw": text
    })

with open(OUT_FILE, "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False, indent=2)

print(f"✅ Индекс тайёр: {len(index)} та файл қўшилди")
