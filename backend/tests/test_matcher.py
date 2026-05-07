"""Tests for the matching engine.

Covers:
  - Normalisation rules (each rule + edge cases)
  - Identical matching (trailing letter, leading zero, hyphen variant, negative)
  - Similar matching (same-category, diff-category rejection, size rejection, trap)
  - End-to-end on a small fixture
"""

import pandas as pd
import pytest

from app.matcher import (
    extract_sizes,
    normalise_code,
    normalise_description,
    run_comparison,
)



class TestNormaliseCode:
    def test_uppercase_and_trim(self):
        assert normalise_code("  abc-123  ") == "ABC123"

    def test_strip_trailing_single_letter(self):
        """PrimeCare catalogue suffix like A2X → A2."""
        assert normalise_code("3M-FLT-Z250-A2X") == normalise_code("3M-FLT-Z250-A2")

    def test_trailing_letter_not_stripped_when_preceded_by_letter(self):
        """Multi-letter suffixes like STD should not be stripped."""
        assert normalise_code("DS-AHP-STD") == "DSAHPSTD"

    def test_leading_zero_stripped(self):
        """SDI-RSC-A2-050 should match SDI-RSC-A2-50."""
        assert normalise_code("SDI-RSC-A2-050") == normalise_code("SDI-RSC-A2-50")

    def test_hyphen_variant(self):
        """DS-PTU-25-F1-3 should match DS-PTU-25-F13 (hyphenation difference)."""
        assert normalise_code("DS-PTU-25-F1-3") == normalise_code("DS-PTU-25-F13")

    def test_letter_o_replaced_with_zero(self):
        """GC-F9-GPX-A2-5O (letter O) should match GC-F9-GPX-A2-50."""
        assert normalise_code("GC-F9-GPX-A2-5O") == normalise_code("GC-F9-GPX-A2-50")

    def test_letter_o_in_all_zeros(self):
        """ND-SE-1OO should match ND-SE-100."""
        assert normalise_code("ND-SE-1OO") == normalise_code("ND-SE-100")

    def test_letter_o_not_replaced_in_alpha_segment(self):
        """Letter O in purely alpha segments (e.g. 'MON') should stay."""
        result = normalise_code("DS-AQU-MON-REG")
        assert "MON" in result

    def test_trailing_g_stripped(self):
        """3M-CAV-28G should match 3M-CAV-28."""
        assert normalise_code("3M-CAV-28G") == normalise_code("3M-CAV-28")

    def test_empty_and_nan(self):
        assert normalise_code("") == ""
        assert normalise_code(None) == ""
        assert normalise_code(float("nan")) == ""


class TestNormaliseDescription:
    def test_basic(self):
        assert normalise_description("  Hello World  ") == "hello world"

    def test_empty(self):
        assert normalise_description("") == ""
        assert normalise_description(None) == ""



class TestExtractSizes:
    def test_clothing_sizes(self):
        assert "xs" in extract_sizes("Gloves Extra Small")
        assert "m" in extract_sizes("Gloves Medium")
        assert "l" in extract_sizes("Gloves Large")

    def test_fractional_size(self):
        sizes = extract_sizes("Gracey Curette 5/6 Double-End")
        assert "5/6" in sizes

    def test_percentage(self):
        sizes = extract_sizes("Opalescence PF 16% Gel")
        assert "16%" in sizes

    def test_ratio(self):
        sizes = extract_sizes("Articaine 1:100000 Cartridges")
        assert "1:100000" in sizes

    def test_mm(self):
        sizes = extract_sizes("ProTaper 25mm Files")
        assert "25mm" in sizes

    def test_no_sizes(self):
        assert extract_sizes("AH Plus Root Canal Sealer") == set()



def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal catalogue DataFrame for testing."""
    cols = [
        "supplier_ref", "product_description", "brand",
        "manufacturer_code", "pack_size", "unit_price_gbp",
        "vat_rate", "category", "notes",
    ]
    for r in rows:
        for c in cols:
            r.setdefault(c, "")
        r.setdefault("unit_price_gbp", 10.0)
    return pd.DataFrame(rows)


class TestIdenticalMatching:
    def test_trailing_letter_match(self):
        """A2X catalogue suffix should still produce identical match."""
        df_a = _make_df([{"manufacturer_code": "3M-FLT-Z250-A2", "category": "Restorative", "unit_price_gbp": 22.10}])
        df_b = _make_df([{"manufacturer_code": "3M-FLT-Z250-A2X", "category": "Restorative", "unit_price_gbp": 22.10}])
        result = run_comparison(df_a, df_b)
        assert result["summary"]["identical_matches"] == 1

    def test_leading_zero_match(self):
        df_a = _make_df([{"manufacturer_code": "SDI-RSC-A2-050", "category": "Restorative", "unit_price_gbp": 54.0}])
        df_b = _make_df([{"manufacturer_code": "SDI-RSC-A2-50", "category": "Restorative", "unit_price_gbp": 54.0}])
        result = run_comparison(df_a, df_b)
        assert result["summary"]["identical_matches"] == 1

    def test_hyphen_variant_match(self):
        df_a = _make_df([{"manufacturer_code": "DS-PTU-25-F13", "category": "Endodontics", "unit_price_gbp": 34.8}])
        df_b = _make_df([{"manufacturer_code": "DS-PTU-25-F1-3", "category": "Endodontics", "unit_price_gbp": 34.8}])
        result = run_comparison(df_a, df_b)
        assert result["summary"]["identical_matches"] == 1

    def test_no_match_different_codes(self):
        """Different products should not match."""
        df_a = _make_df([{"manufacturer_code": "SEP-ART4-100-50", "category": "Anaesthetics", "unit_price_gbp": 28.0}])
        df_b = _make_df([{"manufacturer_code": "SEP-ART4-200-50", "category": "Anaesthetics", "unit_price_gbp": 27.5}])
        result = run_comparison(df_a, df_b)
        assert result["summary"]["identical_matches"] == 0



class TestSimilarMatching:
    def test_same_category_fuzzy_match(self):
        """Similar descriptions in the same category should produce a similar match."""
        df_a = _make_df([{
            "manufacturer_code": "ND-CWR-MD-1000",
            "product_description": "Cotton Wool Rolls Medium",
            "category": "Consumables", "unit_price_gbp": 7.40,
        }])
        df_b = _make_df([{
            "manufacturer_code": "PCM-CWR-MD-1000",
            "product_description": "CottonPlus Rolls Medium",
            "category": "Consumables", "unit_price_gbp": 7.40,
        }])
        result = run_comparison(df_a, df_b)
        assert result["summary"]["identical_matches"] == 0
        assert result["summary"]["similar_matches"] == 1

    def test_different_category_rejected(self):
        """Even with similar descriptions, different categories must not match."""
        df_a = _make_df([{
            "manufacturer_code": "A-001",
            "product_description": "Latex Gloves Medium",
            "category": "PPE", "unit_price_gbp": 6.50,
        }])
        df_b = _make_df([{
            "manufacturer_code": "B-001",
            "product_description": "Latex Gloves Medium",
            "category": "Consumables", "unit_price_gbp": 6.50,
        }])
        result = run_comparison(df_a, df_b)
        assert result["summary"]["identical_matches"] == 0
        assert result["summary"]["similar_matches"] == 0

    def test_same_name_different_size_rejected(self):
        """Gracey 5/6 vs 7/8 — same name, different size → reject."""
        df_a = _make_df([{
            "manufacturer_code": "HF-GR-56-DE",
            "product_description": "Curette Gracey 5/6 Double-End",
            "category": "Instruments", "unit_price_gbp": 38.60,
        }])
        df_b = _make_df([{
            "manufacturer_code": "HF-GR-78-DE",
            "product_description": "Gracey Curette 7/8 Double-End",
            "category": "Instruments", "unit_price_gbp": 38.60,
        }])
        result = run_comparison(df_a, df_b)
        assert result["summary"]["identical_matches"] == 0
        assert result["summary"]["similar_matches"] == 0

    def test_not_a_duplicate_trap_rejected(self):
        """Articaine 1:100000 vs 1:200000 — clinically different, must not match."""
        df_a = _make_df([{
            "manufacturer_code": "SEP-ART4-100-50",
            "product_description": "Septanest 4% Articaine 1:100000 Cartridges",
            "category": "Anaesthetics", "unit_price_gbp": 28.0,
        }])
        df_b = _make_df([{
            "manufacturer_code": "SEP-ART4-200-50",
            "product_description": "Septanest Articaine 4% 1:200000 x50",
            "category": "Anaesthetics", "unit_price_gbp": 27.5,
        }])
        result = run_comparison(df_a, df_b)
        assert result["summary"]["identical_matches"] == 0
        assert result["summary"]["similar_matches"] == 0



class TestEndToEnd:
    def test_small_fixture_counts(self):
        """Run against a small fixture with known expected outcomes."""
        df_a = _make_df([
            {"supplier_ref": "A-001", "manufacturer_code": "MED-NIT-XS-100",
             "product_description": "Nitrile Gloves XS", "category": "PPE", "unit_price_gbp": 7.80},
            {"supplier_ref": "A-002", "manufacturer_code": "3M-FLT-Z250-A2",
             "product_description": "Filtek Z250 A2", "category": "Restorative", "unit_price_gbp": 22.10},
            {"supplier_ref": "A-003", "manufacturer_code": "ND-CWR-MD-1000",
             "product_description": "Cotton Wool Rolls Medium", "category": "Consumables", "unit_price_gbp": 7.40},
            {"supplier_ref": "A-004", "manufacturer_code": "UNIQUE-001",
             "product_description": "Unique Product A", "category": "Equipment", "unit_price_gbp": 99.0},
        ])
        df_b = _make_df([
            {"supplier_ref": "B-001", "manufacturer_code": "MED-NIT-XS-100",
             "product_description": "Nitrile Exam Gloves XS", "category": "PPE", "unit_price_gbp": 8.10},
            {"supplier_ref": "B-002", "manufacturer_code": "3M-FLT-Z250-A2X",
             "product_description": "Filtek Z250 A2", "category": "Restorative", "unit_price_gbp": 22.10},
            {"supplier_ref": "B-003", "manufacturer_code": "PCM-CWR-MD-1000",
             "product_description": "CottonPlus Rolls Medium", "category": "Consumables", "unit_price_gbp": 7.40},
            {"supplier_ref": "B-004", "manufacturer_code": "UNIQUE-002",
             "product_description": "Unique Product B", "category": "Radiography", "unit_price_gbp": 50.0},
        ])
        result = run_comparison(df_a, df_b)

        assert result["summary"]["total_products_a"] == 4
        assert result["summary"]["total_products_b"] == 4
        assert result["summary"]["identical_matches"] == 2
        assert result["summary"]["similar_matches"] == 1
        assert result["summary"]["unmatched_a"] == 1
        assert result["summary"]["unmatched_b"] == 1

        types = {m["product_a"]["supplier_ref"]: m["match_type"] for m in result["matches"]}
        assert types["A-001"] == "identical"
        assert types["A-002"] == "identical"
        assert types["A-003"] == "similar"

    def test_price_difference_calculated(self):
        df_a = _make_df([{"manufacturer_code": "TEST-001", "category": "PPE",
                          "product_description": "Test", "unit_price_gbp": 10.0}])
        df_b = _make_df([{"manufacturer_code": "TEST-001", "category": "PPE",
                          "product_description": "Test", "unit_price_gbp": 8.0}])
        result = run_comparison(df_a, df_b)
        match = result["matches"][0]
        assert match["price_difference_gbp"] == 2.0
        assert match["price_difference_pct"] > 0
