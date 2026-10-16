"""Parse NM OCD Form C-102 (well location plat) and compute lateral length.

Words come from ocr_words(): [(x_center, y_center, height, text, confidence), ...]
"""
import difflib
import math
import re

import easyocr

MILE = 5280
READER = easyocr.Reader(["en"], gpu=False)   # load once per process


# ---------- OCR ----------
def ocr_words(img):
    """Run EasyOCR on a grayscale array and return box centers + text + confidence."""
    out = []
    for box, text, conf in READER.readtext(img):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        out.append((sum(xs) / 4, sum(ys) / 4, max(ys) - min(ys), text.strip(), conf))
    return out


def words_to_text(words):
    """Flatten OCR words into reading order (top-to-bottom, left-to-right)."""
    words = sorted(words, key=lambda w: (round(w[1] / 15), w[0]))
    return " ".join(w[3] for w in words)


# ---------- PLSS geometry ----------
def section_rc(sec):
    """Row/column of a section within its township (sections snake 1-6 right-to-left, 7-12 left-to-right, ...)."""
    row, pos = (sec - 1) // 6, (sec - 1) % 6
    return row, (5 - pos if row % 2 == 0 else pos)


def plss_xy(sec, twp, rng, ft_ns, ns, ft_ew, ew):
    """Approximate x/y in feet for a footage call.

    ns is "NORTH"/"SOUTH", ew is "EAST"/"WEST" (single letters also accepted).
    Assumes South townships and East ranges, which holds for Lea and Eddy counties.
    """
    ns = {"N": "NORTH", "S": "SOUTH"}.get(ns.upper(), ns.upper())
    ew = {"E": "EAST", "W": "WEST"}.get(ew.upper(), ew.upper())
    row, col = section_rc(sec)
    north = -((twp - 1) * 6 + row) * MILE
    west = ((rng - 1) * 6 + col) * MILE
    y = north - ft_ns if ns == "NORTH" else north - MILE + ft_ns
    x = west + MILE - ft_ew if ew == "EAST" else west + ft_ew
    return x, y


# ---------- C-102 parsing ----------
def _direction(tok, options):
    m = difflib.get_close_matches(tok.upper(), options, n=1, cutoff=0.6)
    return m[0] if m else None


def _lead_int(tok):
    m = re.match(r"\s*(\d{1,4})", tok)
    return int(m.group(1)) if m else None


def _row_below(words, anchor_pat):
    """Find the data row under a section title: skip the header line, take the first line with numbers + N/S."""
    anchors = [w for w in words if re.search(anchor_pat, w[3], re.I)]
    if not anchors:
        return None
    _, ay, ah, _, _ = max(anchors, key=lambda w: w[4])
    below = sorted((w for w in words if ay + 0.6 * ah < w[1] < ay + 6 * ah), key=lambda w: w[1])

    lines, cur = [], []
    for w in below:                                  # group words into lines by vertical position
        if cur and w[1] - cur[-1][1] > 0.6 * ah:
            lines.append(cur)
            cur = []
        cur.append(w)
    if cur:
        lines.append(cur)

    for line in lines:
        toks = sorted(line, key=lambda w: w[0])      # left to right
        has_ns = any(_direction(t[3], ["NORTH", "SOUTH"]) for t in toks)
        n_nums = sum(t[3][:1].isdigit() for t in toks)
        if has_ns and n_nums >= 3:
            return toks
    return None


def _parse_row(toks):
    """Columns: UL/Lot, Section, Township, Range, (Lot Idn), Feet, N/S, Feet, E/W, County."""
    texts = [t[3] for t in toks]
    conf = min(t[4] for t in toks)
    i_ns = next((i for i, t in enumerate(texts) if _direction(t, ["NORTH", "SOUTH"])), None)
    i_ew = next((i for i, t in enumerate(texts)
                 if i_ns is not None and i > i_ns and _direction(t, ["EAST", "WEST"])), None)
    if i_ns is None or i_ew is None or i_ns < 4:
        return None

    head = texts[:i_ns - 1]                          # everything before the N/S footage
    if len(head) == 3:
        sec, twp, rng = (_lead_int(t) for t in head)
    else:
        sec, twp, rng = (_lead_int(t) for t in head[1:4])

    return dict(
        section=sec, township=twp, range=rng,
        ft_ns=_lead_int(texts[i_ns - 1]), ns=_direction(texts[i_ns], ["NORTH", "SOUTH"]),
        ft_ew=_lead_int(texts[i_ew - 1]), ew=_direction(texts[i_ew], ["EAST", "WEST"]),
        min_conf=round(float(conf), 2),
    )


def _valid(r):
    return (r is not None and None not in r.values()
            and 1 <= r["section"] <= 36
            and 0 <= r["ft_ns"] <= MILE and 0 <= r["ft_ew"] <= MILE)


def is_c102(text):
    t = text.upper()
    return "DEDICATION PLAT" in t or "ACREAGE DEDICATION" in t or "C-102" in t


def parse_c102(words):
    """Return {'lateral_ft', 'status', 'surface', 'bottom_hole', 'min_conf'} from OCR words of a C-102 page."""
    s = _row_below(words, r"^\W*\d*\W*Surface\s+Location")
    b = _row_below(words, r"Bottom\s+Hole\s+Location")
    surf = _parse_row(s) if s else None
    bh = _parse_row(b) if b else None
    out = {"surface": surf, "bottom_hole": bh, "lateral_ft": None, "status": "ok",
           "min_conf": min((r["min_conf"] for r in (surf, bh) if r), default=None)}

    if not _valid(surf):
        out["status"] = "surface row unreadable"
        return out
    if not _valid(bh):
        out["status"] = "bottom-hole row unreadable (or vertical well)"
        return out
    if abs(bh["township"] - surf["township"]) > 1 or abs(bh["range"] - surf["range"]) > 1:
        out["status"] = "township/range mismatch"
        return out

    key = ("section", "township", "range", "ft_ns", "ns", "ft_ew", "ew")
    sx, sy = plss_xy(*(surf[k] for k in key))
    bx, by = plss_xy(*(bh[k] for k in key))
    out["lateral_ft"] = round(math.hypot(bx - sx, by - sy))
    if not 0 <= out["lateral_ft"] <= 16000:
        out["status"] = "implausible lateral"
    return out