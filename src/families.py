"""Procedure-family nouns ("khai sinh", "kết hôn", "căn cước", …), derived from the titles, not written by hand.

A family is a root procedure and its `variant_of` siblings. Its nouns are the word pairs (accent-folded bigrams) that occur in
every member's title, minus pairs that contain a generic token ("đăng ký", "thực hiện", "cấp", "thẻ" …). Only families with at
least two members are used: a one-member family has every pair of its title in common and would yield noise.

Used by the resolver's `head_noun_guard` (src/nodes.py:choose, flag) and by the insufficient_evidence refusal wording
(src/refusal.py), to tell whether the chosen procedure is of the family the user named.

The table lives in data/family_nouns.json. Regenerate it after a corpus rebuild with
`uv run python -c "from src.families import write_family_nouns; write_family_nouns()"`. tests/test_routing.py checks
that the file equals a fresh derivation from data/app.db.
"""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILY_NOUNS_PATH = ROOT / "data" / "family_nouns.json"
_PREFIX = re.compile(r"^\s*th[uủ]\s*t[uụ]c\s+", re.I)
# generic tokens; "thong tin" and "ho tich" occur across many families' titles (xác nhận thông tin…, trích lục hộ tịch…), and the
# single family 1.004859 (thay đổi, cải chính, bổ sung thông tin hộ tịch, xác định lại dân tộc) otherwise yields fragment pairs
STOP = frozenset("dang ky thuc hien tai cap the thu tuc so xac dinh lai thong tin tich".split())  # not "ho": "giám hộ"
STOP_PAIRS = frozenset({"thong tin", "ho tich"})


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower()).replace("đ", "d")
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def tokens(s: str) -> list[str]:
    return re.findall(r"\w+", _fold(s))


def bigrams(s: str) -> list[str]:
    """Word pairs within each comma/parenthesis-separated part ("thay đổi, cải chính" gives no pair "đổi cải")."""
    out = []
    for part in re.split(r"[,;()]", _PREFIX.sub("", s or "")):
        w = tokens(part)
        out += [" ".join(p) for p in zip(w, w[1:])]
    return out


def derive_family_nouns(rows) -> dict[str, list[str]]:
    """rows: (procedure_id, title, variant_of). Returns {noun: sorted family root ids}."""
    fam: dict[str, list[str]] = {}
    for pid, title, root in rows:
        fam.setdefault(root or pid, []).append(title)
    out: dict[str, set[str]] = {}
    for root, titles in fam.items():
        if len(titles) < 2:
            continue
        common = set.intersection(*(set(bigrams(t)) for t in titles))
        for noun in common:
            if not set(noun.split()) & STOP and noun not in STOP_PAIRS:
                out.setdefault(noun, set()).add(root)
    return {n: sorted(r) for n, r in sorted(out.items())}


def derive_from_db(path: Path | str = ROOT / "data" / "app.db") -> dict[str, list[str]]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return derive_family_nouns(con.execute("SELECT id, title, variant_of FROM procedures").fetchall())
    finally:
        con.close()


def write_family_nouns(path: Path | str = FAMILY_NOUNS_PATH) -> dict[str, list[str]]:
    nouns = derive_from_db()
    Path(path).write_text(json.dumps(nouns, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return nouns


@lru_cache(maxsize=4)
def load_family_nouns(path: str = str(FAMILY_NOUNS_PATH)) -> dict[str, tuple[str, ...]]:
    p = Path(path)
    if not p.exists():
        return {}
    return {n: tuple(r) for n, r in json.loads(p.read_text(encoding="utf-8")).items()}


def nouns_in(text: str, nouns) -> list[tuple[int, str]]:
    """(token position, noun) for every family noun that occurs in `text`, in order of position."""
    w = tokens(text)  # positions over the whole text; a pair across a comma is rare in a hint and harmless here
    found = [(i, f"{a} {b}") for i, (a, b) in enumerate(zip(w, w[1:])) if f"{a} {b}" in nouns]
    seen, out = set(), []
    for i, n in found:
        if n not in seen:
            seen.add(n)
            out.append((i, n))
    return out


def head_noun(text: str, nouns) -> str | None:
    """The first family noun in `text` (the procedure the user names first), or None."""
    hits = nouns_in(text, nouns)
    return hits[0][1] if hits else None


def family_group(noun: str, nouns) -> set[str]:
    """All nouns of the family (or families) that `noun` names: "giám hộ" also covers "chấm dứt"."""
    fams = set(nouns.get(noun, ()))
    return {m for m, r in nouns.items() if set(r) & fams} or {noun}


def title_has(title: str, family_nouns_of_group: set[str]) -> bool:
    return bool(set(bigrams(title)) & family_nouns_of_group)
