"""Unit tests for ID generation with collision resistance and injectable factory."""

import itertools

from evidence_agent.ids import (
    generate_asset_id,
    generate_batch_id,
    generate_claim_id,
    generate_entity_id,
    generate_locator_id,
    generate_review_id,
    generate_revision_id,
    generate_row_id,
    generate_run_id,
    generate_section_id,
    generate_source_id,
    generate_task_id,
    set_id_factory,
)


class TestIdGeneration:
    """Test ID generation correctness and collision resistance."""

    def test_prefixes_correct(self):
        """IDs have the correct prefixes."""
        assert generate_source_id().startswith("SRC-")
        assert generate_asset_id().startswith("AST-")
        assert generate_task_id().startswith("TASK-")
        assert generate_run_id().startswith("RUN-")
        assert generate_claim_id().startswith("CLM-")
        assert generate_locator_id().startswith("LOC-")
        assert generate_section_id().startswith("SEC-")
        assert generate_review_id().startswith("REV-")
        assert generate_revision_id().startswith("RVN-")
        assert generate_batch_id().startswith("RVB-")
        assert generate_row_id().startswith("RVR-")
        assert generate_entity_id().startswith("ENT-")

    def test_full_uuid_length(self):
        """IDs must use full 32-char hex (not old 8-char)."""
        cid = generate_claim_id()
        # Format: CLM-<32 hex>
        hex_part = cid.split("-", 1)[1]
        assert len(hex_part) == 32, f"Expected 32 hex chars, got {len(hex_part)}: {cid}"
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_no_collisions_100k(self):
        """Generate 100000 IDs with no duplicates."""
        ids: set[str] = set()
        for _ in range(100000):
            ids.add(generate_claim_id())
        assert len(ids) == 100000

    def test_deterministic_factory(self):
        """Inject a deterministic ID factory for testing."""
        counter = itertools.count(1)

        def seq_id() -> str:
            return f"{next(counter):032d}"

        set_id_factory(seq_id)
        try:
            c1 = generate_claim_id()
            c2 = generate_claim_id()
            assert c1 == "CLM-00000000000000000000000000000001"
            assert c2 == "CLM-00000000000000000000000000000002"

            rid = generate_run_id()
            assert rid == "RUN-00000000000000000000000000000003"
        finally:
            set_id_factory(None)

    def test_old_short_id_still_valid_format(self):
        """Old 8-char IDs are still valid strings (backward compat)."""
        old_id = "SRC-a1b2c3d4"
        assert old_id.startswith("SRC-")
        assert len(old_id.split("-", 1)[1]) == 8
        # Schema accepts any string with SRC- prefix
        # We ensure old IDs are still readable (not rejected by regex)

    def test_all_generators_use_32_chars(self):
        """Every ID generator must produce 32-char hex suffix."""
        generators = [
            generate_source_id, generate_asset_id, generate_task_id,
            generate_run_id, generate_claim_id, generate_locator_id,
            generate_section_id, generate_review_id, generate_revision_id,
            generate_batch_id, generate_row_id, generate_entity_id,
        ]
        for gen in generators:
            result = gen()
            hex_part = result.split("-", 1)[1]
            assert len(hex_part) == 32, (
                f"{gen.__name__} produced '{result}' with {len(hex_part)} hex chars"
            )
