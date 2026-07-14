"""Unit tests for DeepSeek response parser."""

import json

from evidence_agent.extraction.response_parser import parse_claim_response


class TestParseClaimResponse:
    """Test parsing of LLM responses into claims."""

    # ── Valid cases ─────────────────────────────────

    def test_valid_claims(self):
        raw = json.dumps(
            {
                "claims": [
                    {
                        "claim_type": "reported_result",
                        "source_quote": "The solubility increased from 1.0 to 5.2 mg/mL.",
                        "faithful_paraphrase": "溶解度从 1.0 增加到 5.2 mg/mL。",
                        "evidence_basis_description": "基于 Figure 1。",
                        "scope_description": None,
                        "author_hedging": None,
                        "locator_hint": {"page": 1},
                        "entities": [],
                    }
                ]
            }
        )
        result = parse_claim_response(raw)
        assert result["status"] == "ok"
        assert len(result["claims"]) == 1
        assert result["claims"][0]["claim_type"] == "reported_result"

    def test_empty_claims_array(self):
        raw = json.dumps({"claims": []})
        result = parse_claim_response(raw)
        assert result["status"] == "empty"
        assert len(result["claims"]) == 0

    def test_top_level_array(self):
        """Model returns claims as a top-level array."""
        raw = json.dumps(
            [
                {
                    "claim_type": "reported_result",
                    "source_quote": "Test quote.",
                    "faithful_paraphrase": "Test paraphrase.",
                    "evidence_basis_description": "Test basis.",
                }
            ]
        )
        result = parse_claim_response(raw)
        assert result["status"] == "ok"
        assert len(result["claims"]) == 1

    # ── Markdown fence ──────────────────────────────

    def test_markdown_fence(self):
        raw = (
            '```json\n'
            '{"claims": [{"claim_type": "reported_result", '
            '"source_quote": "Test.", "faithful_paraphrase": "P.", '
            '"evidence_basis_description": "B."}]}\n'
            '```'
        )
        result = parse_claim_response(raw)
        assert result["status"] == "ok"
        assert len(result["claims"]) == 1

    # ── Invalid cases ───────────────────────────────

    def test_invalid_json(self):
        result = parse_claim_response("not valid json {")
        assert result["status"] == "invalid_json"
        assert len(result["claims"]) == 0

    def test_claims_not_array(self):
        raw = json.dumps({"claims": "not an array"})
        result = parse_claim_response(raw)
        assert result["status"] == "invalid_json"

    def test_empty_response(self):
        result = parse_claim_response("")
        assert result["status"] == "empty"

    def test_whitespace_only_response(self):
        result = parse_claim_response("   \n  ")
        assert result["status"] == "empty"

    def test_missing_required_fields(self):
        raw = json.dumps(
            {
                "claims": [
                    {
                        "claim_type": "reported_result",
                        "source_quote": "",
                        "faithful_paraphrase": "",
                        "evidence_basis_description": "",
                    }
                ]
            }
        )
        result = parse_claim_response(raw)
        assert result["status"] == "invalid_schema"
        assert len(result["claims"]) == 0

    def test_invalid_claim_type(self):
        raw = json.dumps(
            {
                "claims": [
                    {
                        "claim_type": "made_up_type",
                        "source_quote": "Test.",
                        "faithful_paraphrase": "P.",
                        "evidence_basis_description": "B.",
                    }
                ]
            }
        )
        result = parse_claim_response(raw)
        assert result["status"] == "invalid_schema"

    def test_mixed_valid_and_invalid(self):
        """Some valid claims, some invalid — only valid ones returned."""
        raw = json.dumps(
            {
                "claims": [
                    {
                        "claim_type": "reported_result",
                        "source_quote": "Valid quote.",
                        "faithful_paraphrase": "Valid paraphrase.",
                        "evidence_basis_description": "Valid basis.",
                    },
                    {
                        "claim_type": "reported_result",
                        "source_quote": "",
                        "faithful_paraphrase": "",
                        "evidence_basis_description": "",
                    },
                ]
            }
        )
        result = parse_claim_response(raw)
        assert result["status"] == "ok"
        assert len(result["claims"]) == 1
        assert len(result["errors"]) >= 1

    def test_truncated_json(self):
        raw = '{"claims": [{"claim_type": "reported_result", "source_qu'
        result = parse_claim_response(raw)
        assert result["status"] == "invalid_json"
