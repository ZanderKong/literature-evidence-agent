"""Golden set: expected claim patterns for bilingual fidelity evaluation.

32 total: 24 positive (expected to be extracted), 8 negative (must NOT be extracted).
Covers 9 claim types, hedging, scope.
"""
import json
from pathlib import Path

GOLDEN_DIR = Path(__file__).resolve().parent


def load_golden() -> list[dict]:
    path = GOLDEN_DIR / "golden_set.json"
    if path.exists():
        return json.loads(path.read_text())
    return _build_default_golden()


def _build_default_golden() -> list[dict]:
    """Build default 32-item golden set from existing test fixtures."""
    items = [
        # ── English positive cases (24 items) ──
        # background_statement
        {"label": "positive", "pattern": "HP-β-CD", "claim_type": "background_statement",
         "source": "EN", "quote_required": True, "locator_required": True},
        {"label": "positive", "pattern": "solubil", "claim_type": "background_statement",
         "source": "EN", "quote_required": True},
        # method_statement
        {"label": "positive", "pattern": "prepar", "claim_type": "method_statement",
         "source": "EN", "quote_required": True, "locator_required": True},
        {"label": "positive", "pattern": "dissolv", "claim_type": "method_statement",
         "source": "EN", "quote_required": True},
        # reported_observation
        {"label": "positive", "pattern": "observ", "claim_type": "reported_observation",
         "source": "EN", "quote_required": True, "locator_required": True},
        {"label": "positive", "pattern": "chang", "claim_type": "reported_observation",
         "source": "EN", "quote_required": True},
        # reported_result
        {"label": "positive", "pattern": "result", "claim_type": "reported_result",
         "source": "EN", "quote_required": True, "locator_required": True},
        {"label": "positive", "pattern": "increas", "claim_type": "reported_result",
         "source": "EN", "quote_required": True},
        {"label": "positive", "pattern": "fold", "claim_type": "reported_result",
         "source": "EN", "quote_required": True, "locator_required": True},
        # author_interpretation
        {"label": "positive", "pattern": "suggest", "claim_type": "author_interpretation",
         "source": "EN", "quote_required": True, "hedging": True},
        {"label": "positive", "pattern": "indicate", "claim_type": "author_interpretation",
         "source": "EN", "quote_required": True, "hedging": True},
        # author_conclusion
        {"label": "positive", "pattern": "conclusion", "claim_type": "author_conclusion",
         "source": "EN", "quote_required": True, "locator_required": True},
        {"label": "positive", "pattern": "demonstrat", "claim_type": "author_conclusion",
         "source": "EN", "quote_required": True},
        # author_hypothesis
        {"label": "positive", "pattern": "hypothes", "claim_type": "author_hypothesis",
         "source": "EN", "hedging": True},
        {"label": "positive", "pattern": "may be due", "claim_type": "author_hypothesis",
         "source": "EN", "hedging": True},
        # author_limitation
        {"label": "positive", "pattern": "limit", "claim_type": "author_limitation",
         "source": "EN", "quote_required": True},
        {"label": "positive", "pattern": "further", "claim_type": "author_limitation",
         "source": "EN"},
        # future_work
        {"label": "positive", "pattern": "need", "claim_type": "future_work",
         "source": "EN", "hedging": True},
        {"label": "positive", "pattern": "study", "claim_type": "future_work",
         "source": "EN"},
        # scope
        {"label": "positive", "pattern": "in vitro", "claim_type": "reported_result",
         "source": "EN", "quote_required": True, "scope": True},
        {"label": "positive", "pattern": "concentrat", "claim_type": "reported_result",
         "source": "EN", "quote_required": True, "scope": True},
        {"label": "positive", "pattern": "ratio", "claim_type": "reported_result",
         "source": "EN", "quote_required": True},
        {"label": "positive", "pattern": "method", "claim_type": "method_statement",
         "source": "EN", "quote_required": True},
        {"label": "positive", "pattern": "analys", "claim_type": "method_statement",
         "source": "EN", "quote_required": True},

        # ── English negative cases (8 items) ──
        {"label": "negative", "pattern": "ZXZXYNOTEXIST", "source": "EN",
         "note": "Nonexistent term — must not appear"},
        {"label": "negative", "pattern": "quantum entanglement", "source": "EN",
         "note": "Unrelated physics term"},
        {"label": "negative", "pattern": "", "claim_type": "reported_result",
         "source": "EN", "note": "Empty pattern — should match nothing"},
        {"label": "negative", "pattern": "Copyright 2005", "source": "EN",
         "note": "Metadata, not a claim"},
        {"label": "negative", "pattern": "et al.", "source": "EN",
         "note": "Citation, not a claim"},
        {"label": "negative", "pattern": "Figure 1", "source": "EN",
         "note": "Label, not a claim"},
        {"label": "negative", "pattern": "corresponding author", "source": "EN",
         "note": "Administrative text"},
        {"label": "negative", "pattern": "Table of contents", "source": "EN",
         "note": "TOC entry, not a claim"},
    ]
    return items
