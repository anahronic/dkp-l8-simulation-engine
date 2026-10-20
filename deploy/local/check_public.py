"""Fail closed on private paths/markers or copied translation passages, including nested archives."""
import io
import json
from pathlib import Path
import sys
import tarfile
import zipfile

MARKERS = (b"private_do_not_publish", b"search_ru", b"ru-sources", b"corpus.jsonl")


def private_passages(corpus=None, ru=None):
    texts = []
    if corpus:
        texts.extend(json.loads(line).get("search_ru", "") for line in Path(corpus).read_text(encoding="utf-8").splitlines())
    if ru:
        texts.extend(p.read_text(encoding="utf-8") for p in Path(ru).rglob("*.md"))
    spans = set()
    for text in texts:
        text = " ".join(text.split()).casefold()
        if len(text) >= 80:
            spans.update(text[i:i + 80] for i in range(0, len(text) - 79, 40))
    # Untranslated English passages (formulas, JSON, identifiers) are copies of the public canon, not translation:
    # a span is a translation passage only if it is mostly Cyrillic text.
    return {s for s in spans if sum("а" <= ch <= "я" or ch == "ё" for ch in s) >= 20}


def check_blob(name, data, spans=(), depth=0):
    if depth > 5 or len(data) > 200_000_000:
        raise ValueError("Public archive nesting/size limit")
    if any(m in name.casefold().encode() or m in data.lower() for m in MARKERS):
        raise ValueError("Private marker in public artifact: " + name)
    text = " ".join(data.decode("utf-8", "ignore").split()).casefold()
    if any(span in text for span in spans):
        raise ValueError("Translation passage in public artifact: " + name)
    stream = io.BytesIO(data)
    if zipfile.is_zipfile(stream):
        with zipfile.ZipFile(stream) as archive:
            for item in archive.infolist():
                if item.file_size > 200_000_000:
                    raise ValueError("Oversized ZIP member")
                check_blob(name + "/" + item.filename, archive.read(item), spans, depth + 1)
    elif name.lower().endswith((".tar.gz", ".tgz", ".tar")):
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for item in archive:
                if item.isdir():
                    check_blob(name + "/" + item.name, b"", spans, depth + 1)
                elif item.isfile() and item.size <= 200_000_000:
                    check_blob(name + "/" + item.name, archive.extractfile(item).read(), spans, depth + 1)
                else:
                    raise ValueError("Nonregular/oversized public archive member")


if __name__ == "__main__":
    path = Path(sys.argv[1])
    check_blob(path.name, path.read_bytes(), private_passages(*sys.argv[2:]))
    print("Public archive privacy check passed")
