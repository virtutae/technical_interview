"""Two-pass product matching engine.

Pass 1 — Identical: normalise manufacturer codes and match on equality.
Pass 2 — Similar:  fuzzy description matching within the same category,
                   guarded by a size-extraction check to avoid false positives.
"""

import re
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

SIMILARITY_THRESHOLD = 85

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"



def normalise_code(code: str) -> str:
    """Normalise a manufacturer code for comparison.

    Steps:
      1. Uppercase + trim
      2. Split on hyphens / dashes
      3. In segments that contain a digit, replace letter-O with zero
      4. Strip leading zeros from purely numeric segments
      5. Rejoin *without* hyphens (removes hyphenation differences)
      6. Strip a single trailing letter (catalogue suffixes like 'X')
    """
    if not code or (isinstance(code, float) and pd.isna(code)):
        return ""
    code = str(code).strip().upper()

    segments = re.split(r"[-–—]", code)
    normalised = []
    for seg in segments:
        if any(c.isdigit() for c in seg):
            seg = seg.replace("O", "0")
        if seg.isdigit():
            seg = str(int(seg))
        normalised.append(seg)

    result = "".join(normalised)

    if len(result) > 1 and result[-1].isalpha() and not result[-2].isalpha():
        result = result[:-1]

    return result


def normalise_description(desc: str) -> str:
    """Lowercase + trim a product description."""
    if not desc or (isinstance(desc, float) and pd.isna(desc)):
        return ""
    return str(desc).strip().lower()


_SIZE_WORD_MAP = [
    (r"\bextra[\s-]*small\b", "xs"),
    (r"\bx[\s-]*small\b", "xs"),
    (r"\bextra[\s-]*large\b", "xl"),
    (r"\bx[\s-]*large\b", "xl"),
    (r"\bmedium\b", "m"),
    (r"\bsmall\b", "s"),
    (r"\blarge\b", "l"),
]


def extract_sizes(desc: str) -> set[str]:
    """Pull size indicators out of a description for the size guardrail.

    Captures: clothing sizes (XS-XL), fractional sizes (5/6),
    ratios (1:100000), percentages (16%), lengths (25mm).
    """
    d = desc.lower()
    sizes: set[str] = set()

    for pattern, label in _SIZE_WORD_MAP:
        if re.search(pattern, d):
            sizes.add(label)

    sizes.update(re.findall(r"\b(\d+/\d+)\b", d))          # 5/6, 7/8
    sizes.update(re.findall(r"\b(\d+:\d+)\b", d))           # 1:100000
    sizes.update(re.findall(r"(\d+(?:\.\d+)?%)", d))        # 16%, 0.2%
    sizes.update(re.findall(r"(\d+mm)\b", d))               # 25mm

    return sizes



def load_catalogues() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the two supplier CSV files from the data/ directory."""
    df_a = pd.read_csv(DATA_DIR / "novadent_catalogue.csv")
    df_b = pd.read_csv(DATA_DIR / "primecare_catalogue.csv")
    return df_a, df_b



def _clean_notes(val: str) -> str:
    """Strip stray leading commas and whitespace from notes."""
    s = str(val).strip().lstrip(",").strip()
    return s


def _product_dict(row: pd.Series) -> dict:
    """Convert a catalogue row into the API product shape."""
    return {
        "supplier_ref": row["supplier_ref"],
        "product_description": row["product_description"],
        "brand": row["brand"],
        "manufacturer_code": row["manufacturer_code"],
        "pack_size": row["pack_size"],
        "unit_price_gbp": float(row["unit_price_gbp"]),
        "vat_rate": row["vat_rate"],
        "category": row["category"],
        "notes": _clean_notes(row["notes"]) if "notes" in row.index and pd.notna(row["notes"]) else "",
    }


def _make_match(row_a: pd.Series, row_b: pd.Series,
                match_type: str, confidence) -> dict:
    price_a = float(row_a["unit_price_gbp"])
    price_b = float(row_b["unit_price_gbp"])
    diff = round(price_a - price_b, 2)
    avg = (price_a + price_b) / 2
    pct = round((diff / avg) * 100, 2) if avg else 0.0
    return {
        "match_type": match_type,
        "confidence": confidence,
        "score": None if match_type == "identical" else round(confidence, 1),
        "product_a": _product_dict(row_a),
        "product_b": _product_dict(row_b),
        "price_difference_gbp": diff,
        "price_difference_pct": pct,
    }


def run_comparison(df_a: pd.DataFrame, df_b: pd.DataFrame) -> dict:
    """Execute the two-pass matching algorithm and return the API response."""
    df_a = df_a.copy()
    df_b = df_b.copy()
    df_a["norm_code"] = df_a["manufacturer_code"].apply(normalise_code)
    df_b["norm_code"] = df_b["manufacturer_code"].apply(normalise_code)
    df_a["norm_desc"] = df_a["product_description"].apply(normalise_description)
    df_b["norm_desc"] = df_b["product_description"].apply(normalise_description)

    matches: list[dict] = []
    matched_a: set[int] = set()
    matched_b: set[int] = set()

    code_to_b: dict[str, list[int]] = {}
    for j, row_b in df_b.iterrows():
        nc = row_b["norm_code"]
        if nc:
            code_to_b.setdefault(nc, []).append(j)

    for i, row_a in df_a.iterrows():
        nc = row_a["norm_code"]
        if not nc or nc not in code_to_b:
            continue
        for j in code_to_b[nc]:
            if j not in matched_b:
                matches.append(_make_match(row_a, df_b.loc[j], "identical", "high"))
                matched_a.add(i)
                matched_b.add(j)
                break

    remaining_a = df_a[~df_a.index.isin(matched_a)]
    remaining_b_indices = [j for j in df_b.index if j not in matched_b]

    for i, row_a in remaining_a.iterrows():
        best_score = 0
        best_j = None

        for j in remaining_b_indices:
            if j in matched_b:
                continue
            row_b = df_b.loc[j]

            if row_a["category"] != row_b["category"]:
                continue

            score = fuzz.token_set_ratio(row_a["norm_desc"], row_b["norm_desc"])
            if score < SIMILARITY_THRESHOLD:
                continue

            sizes_a = extract_sizes(row_a["product_description"])
            sizes_b = extract_sizes(row_b["product_description"])
            if sizes_a and sizes_b and sizes_a != sizes_b:
                continue

            if score > best_score:
                best_score = score
                best_j = j

        if best_j is not None:
            matches.append(
                _make_match(row_a, df_b.loc[best_j], "similar", best_score)
            )
            matched_a.add(i)
            matched_b.add(best_j)

    identical_count = sum(1 for m in matches if m["match_type"] == "identical")
    similar_count = sum(1 for m in matches if m["match_type"] == "similar")

    unmatched_a = [
        _product_dict(df_a.loc[i])
        for i in df_a.index if i not in matched_a
    ]
    unmatched_b = [
        _product_dict(df_b.loc[j])
        for j in df_b.index if j not in matched_b
    ]

    return {
        "summary": {
            "total_products_a": len(df_a),
            "total_products_b": len(df_b),
            "identical_matches": identical_count,
            "similar_matches": similar_count,
            "unmatched_a": len(unmatched_a),
            "unmatched_b": len(unmatched_b),
        },
        "matches": matches,
        "unmatched_a": unmatched_a,
        "unmatched_b": unmatched_b,
    }
