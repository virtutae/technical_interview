"""FastAPI application – serves the /comparisons endpoint."""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from .matcher import load_catalogues, run_comparison

app = FastAPI(
    title="Dentstock Price Comparison",
    description="Compare dental supplier catalogues to find identical and similar products.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_result: dict = {}


@app.on_event("startup")
def _startup() -> None:
    global _result
    df_a, df_b = load_catalogues()
    _result = run_comparison(df_a, df_b)


@app.get("/comparisons")
def get_comparisons(
    match_type: str | None = Query(None, description="Filter by match type: identical or similar"),
    min_score: float | None = Query(None, description="Minimum similarity score (for similar matches)"),
) -> dict:
    """Return product comparison results with optional filters."""
    matches = _result["matches"]

    if match_type:
        matches = [m for m in matches if m["match_type"] == match_type]

    if min_score is not None:
        matches = [m for m in matches if m["score"] is not None and m["score"] >= min_score]

    identical = sum(1 for m in matches if m["match_type"] == "identical")
    similar = sum(1 for m in matches if m["match_type"] == "similar")

    return {
        "summary": {
            **_result["summary"],
            "identical_matches": identical,
            "similar_matches": similar,
        },
        "matches": matches,
        "unmatched_a": _result.get("unmatched_a", []),
        "unmatched_b": _result.get("unmatched_b", []),
    }
