"""Unit tests for all Pydantic schemas."""

import pytest
from pydantic import ValidationError

from evidence_agent.schemas.claim import (
    ClaimLocator,
    ClaimType,
    Entity,
    EntityType,
    LocatorConfidence,
    RecordReviewStatus,
    ScientificVerificationStatus,
    SourceClaim,
)
from evidence_agent.schemas.review import (
    ClaimRevision,
    ReviewDecision,
    ReviewDecisionRecord,
    ReviewObjectType,
)
from evidence_agent.schemas.run import ProcessingRun, RunStatus
from evidence_agent.schemas.section import Section
from evidence_agent.schemas.source import (
    ScientificVerificationStatus as SourceSciStatus,
)
from evidence_agent.schemas.source import (
    Source,
    SourceAsset,
    SourceType,
)
from evidence_agent.schemas.task import (
    AnalysisDepth,
    ResearchTask,
    TaskMode,
    TaskStatus,
)

# ── Task ──────────────────────────────────────────────

class TestResearchTask:
    def test_valid_task(self):
        t = ResearchTask(
            task_id="TASK-000001",
            title="Test task",
            user_request="Analyze something",
            task_mode=TaskMode.ANALYSE_UPLOADED,
            analysis_depth=AnalysisDepth.TASK_FOCUSED,
        )
        assert t.task_id == "TASK-000001"
        assert t.status == TaskStatus.CREATED

    def test_invalid_mode(self):
        with pytest.raises(ValidationError):
            ResearchTask(
                task_id="TASK-000001",
                title="Test",
                user_request="Test",
                task_mode="invalid_mode",
                analysis_depth=AnalysisDepth.TASK_FOCUSED,
            )

    def test_invalid_depth(self):
        with pytest.raises(ValidationError):
            ResearchTask(
                task_id="TASK-000001",
                title="Test",
                user_request="Test",
                task_mode=TaskMode.ANALYSE_UPLOADED,
                analysis_depth="invalid_depth",
            )


# ── Source ─────────────────────────────────────────────

class TestSource:
    def test_valid_source(self):
        s = Source(
            source_id="SRC-000001",
            source_type=SourceType.JOURNAL_ARTICLE,
            original_file_sha256="a" * 64,
        )
        assert s.origin_scope == "external"
        assert s.scientific_verification_status == SourceSciStatus.UNVERIFIED

    def test_origin_must_be_external(self):
        with pytest.raises(ValidationError):
            Source(
                source_id="SRC-000001",
                source_type=SourceType.JOURNAL_ARTICLE,
                original_file_sha256="a" * 64,
                origin_scope="internal",
            )

    def test_scientific_status_must_be_unverified(self):
        with pytest.raises(ValidationError):
            Source(
                source_id="SRC-000001",
                source_type=SourceType.JOURNAL_ARTICLE,
                original_file_sha256="a" * 64,
                scientific_verification_status=(
                    SourceSciStatus.INTERNALLY_REPRODUCED
                ),
            )

    def test_invalid_source_type(self):
        with pytest.raises(ValidationError):
            Source(
                source_id="SRC-000001",
                source_type="blog_post",
                original_file_sha256="a" * 64,
            )


class TestSourceAsset:
    def test_valid_asset(self):
        a = SourceAsset(
            asset_id="AST-000001",
            source_id="SRC-000001",
            asset_type="main_document",
            relative_path="original/main.pdf",
            mime_type="application/pdf",
            sha256="b" * 64,
            file_size=1024,
        )
        assert a.file_size == 1024

    def test_negative_file_size(self):
        with pytest.raises(ValidationError):
            SourceAsset(
                asset_id="AST-000001",
                source_id="SRC-000001",
                asset_type="main_document",
                relative_path="original/main.pdf",
                mime_type="application/pdf",
                sha256="b" * 64,
                file_size=-1,
            )


# ── Section ────────────────────────────────────────────

class TestSection:
    def test_valid_section(self):
        s = Section(
            section_id="SEC-000001",
            source_id="SRC-000001",
            section_type="introduction",
            heading="Introduction",
            page_start=1,
            page_end=2,
            sequence_number=1,
            text="This is intro text.",
            parser_name="pdfplumber",
            parser_version="1.0",
            text_sha256="c" * 64,
        )
        assert s.section_id == "SEC-000001"

    def test_page_end_lt_page_start(self):
        with pytest.raises(ValidationError):
            Section(
                section_id="SEC-000001",
                source_id="SRC-000001",
                section_type="introduction",
                page_start=5,
                page_end=3,
                sequence_number=1,
                text="Text",
                parser_name="pdfplumber",
                parser_version="1.0",
                text_sha256="c" * 64,
            )

    def test_empty_text(self):
        with pytest.raises(ValidationError):
            Section(
                section_id="SEC-000001",
                source_id="SRC-000001",
                section_type="introduction",
                sequence_number=1,
                text="   ",
                parser_name="pdfplumber",
                parser_version="1.0",
                text_sha256="c" * 64,
            )


# ── Claim (core) ───────────────────────────────────────

class TestSourceClaim:
    def test_valid_claim(self):
        c = SourceClaim(
            claim_id="CLM-000001",
            source_id="SRC-000001",
            claim_type=ClaimType.RESULT,
            source_quote="The solubility increased.",
            faithful_paraphrase="溶解度提高了。",
            evidence_basis_description="Based on Figure 1.",
            created_by_run_id="RUN-000001",
        )
        assert c.origin_scope == "external"
        assert (
            c.scientific_verification_status
            == ScientificVerificationStatus.UNVERIFIED
        )
        assert c.record_review_status == RecordReviewStatus.PENDING

    def test_empty_quote(self):
        with pytest.raises(ValidationError):
            SourceClaim(
                claim_id="CLM-000001",
                source_id="SRC-000001",
                claim_type=ClaimType.RESULT,
                source_quote="",
                faithful_paraphrase="paraphrase",
                evidence_basis_description="basis",
                created_by_run_id="RUN-000001",
            )

    def test_empty_paraphrase(self):
        with pytest.raises(ValidationError):
            SourceClaim(
                claim_id="CLM-000001",
                source_id="SRC-000001",
                claim_type=ClaimType.RESULT,
                source_quote="quote",
                faithful_paraphrase="",
                evidence_basis_description="basis",
                created_by_run_id="RUN-000001",
            )

    def test_invalid_claim_type(self):
        with pytest.raises(ValidationError):
            SourceClaim(
                claim_id="CLM-000001",
                source_id="SRC-000001",
                claim_type="made_up_type",
                source_quote="quote",
                faithful_paraphrase="paraphrase",
                evidence_basis_description="basis",
                created_by_run_id="RUN-000001",
            )

    def test_origin_not_external(self):
        with pytest.raises(ValidationError):
            SourceClaim(
                claim_id="CLM-000001",
                source_id="SRC-000001",
                claim_type=ClaimType.RESULT,
                source_quote="quote",
                faithful_paraphrase="paraphrase",
                evidence_basis_description="basis",
                created_by_run_id="RUN-000001",
                origin_scope="internal",
            )

    def test_invalid_scientific_status(self):
        with pytest.raises(ValidationError):
            SourceClaim(
                claim_id="CLM-000001",
                source_id="SRC-000001",
                claim_type=ClaimType.RESULT,
                source_quote="quote",
                faithful_paraphrase="paraphrase",
                evidence_basis_description="basis",
                created_by_run_id="RUN-000001",
                scientific_verification_status=(
                    ScientificVerificationStatus.INTERNALLY_REPRODUCED
                ),
            )

    def test_invalid_review_status(self):
        with pytest.raises(ValidationError):
            SourceClaim(
                claim_id="CLM-000001",
                source_id="SRC-000001",
                claim_type=ClaimType.RESULT,
                source_quote="quote",
                faithful_paraphrase="paraphrase",
                evidence_basis_description="basis",
                created_by_run_id="RUN-000001",
                record_review_status="published",
            )

    def test_invalid_quote_match_status(self):
        with pytest.raises(ValidationError):
            SourceClaim(
                claim_id="CLM-000001",
                source_id="SRC-000001",
                claim_type=ClaimType.RESULT,
                source_quote="quote",
                faithful_paraphrase="paraphrase",
                evidence_basis_description="basis",
                created_by_run_id="RUN-000001",
                quote_match_status="fuzzy",
            )

    # ── valid examples from contract ──

    def test_reported_result_example(self):
        sol_quote = (
            "The solubility of curcumin increased from 0.6 μg/mL "
            "to 3.2 mg/mL upon complexation with HP-β-CD "
            "at a 1:2 molar ratio."
        )
        c = SourceClaim(
            claim_id="CLM-000001",
            source_id="SRC-000001",
            claim_type=ClaimType.RESULT,
            source_quote=sol_quote,
            faithful_paraphrase=(
                "姜黄素与 HP-β-CD 以 1:2 摩尔比络合后，"
                "溶解度从 0.6 μg/mL 增加至 3.2 mg/mL。"
            ),
            evidence_basis_description=(
                "作者通过相溶解度实验测量，数据见 Table 1 和 Figure 2A。"
            ),
            scope_description=(
                "适用于姜黄素与 HP-β-CD 在水溶液体系中 25°C 条件下的络合。"
            ),
            created_by_run_id="RUN-000001",
        )
        assert c.claim_type == ClaimType.RESULT

    def test_author_interpretation_example(self):
        intrp_quote = (
            "This suggests that the aromatic ring of curcumin "
            "is deeply inserted into the hydrophobic cavity of HP-β-CD."
        )
        c = SourceClaim(
            claim_id="CLM-000002",
            source_id="SRC-000001",
            claim_type=ClaimType.INTERPRETATION,
            source_quote=intrp_quote,
            faithful_paraphrase="作者提出姜黄素芳香环深深插入 HP-β-CD 疏水空腔。",
            evidence_basis_description="基于 FT-IR 光谱和 NMR。",
            author_hedging="suggests",
            created_by_run_id="RUN-000001",
        )
        assert c.author_hedging == "suggests"

    def test_author_limitation_example(self):
        c = SourceClaim(
            claim_id="CLM-000003",
            source_id="SRC-000001",
            claim_type=ClaimType.LIMITATION,
            source_quote=(
                "However, the in vitro dissolution results "
                "may not directly predict in vivo performance."
            ),
            faithful_paraphrase=(
                "作者指出体外溶出结果可能无法直接预测体内表现。"
            ),
            evidence_basis_description="作者基于常规认知提出的谨慎说明。",
            author_hedging="may not",
            created_by_run_id="RUN-000001",
        )
        assert c.claim_type == ClaimType.LIMITATION

    def test_empty_quote_rejected(self):
        with pytest.raises(ValidationError):
            SourceClaim(
                claim_id="CLM-000004",
                source_id="SRC-000001",
                claim_type=ClaimType.RESULT,
                source_quote="",
                faithful_paraphrase="溶解度提高了。",
                evidence_basis_description="basis",
                created_by_run_id="RUN-000001",
            )


class TestClaimLocator:
    def test_valid_locator(self):
        loc = ClaimLocator(
            locator_id="LOC-000001",
            claim_id="CLM-000001",
            page=5,
            locator_confidence=LocatorConfidence.HIGH,
        )
        assert loc.page == 5

    def test_invalid_confidence(self):
        with pytest.raises(ValidationError):
            ClaimLocator(
                locator_id="LOC-000001",
                claim_id="CLM-000001",
                page=5,
                locator_confidence="very_high",
            )

    def test_char_end_lt_start(self):
        with pytest.raises(ValidationError):
            ClaimLocator(
                locator_id="LOC-000001",
                claim_id="CLM-000001",
                character_start=100,
                character_end=50,
                locator_confidence=LocatorConfidence.HIGH,
            )


# ── Review ─────────────────────────────────────────────

class TestReviewDecision:
    def test_valid_approve(self):
        r = ReviewDecisionRecord(
            review_id="REV-000001",
            object_type=ReviewObjectType.CLAIM,
            object_id="CLM-000001",
            decision=ReviewDecision.APPROVE,
            original_content_json="{}",
            reviewer="磁带",
        )
        assert r.decision == ReviewDecision.APPROVE

    def test_valid_approve_with_edits(self):
        r = ReviewDecisionRecord(
            review_id="REV-000002",
            object_type=ReviewObjectType.CLAIM,
            object_id="CLM-000001",
            decision=ReviewDecision.APPROVE_WITH_EDITS,
            original_content_json="{}",
            edited_content_json='{"source_quote":"corrected"}',
            reviewer="磁带",
        )
        assert r.edited_content_json is not None

    def test_valid_reject(self):
        r = ReviewDecisionRecord(
            review_id="REV-000003",
            object_type=ReviewObjectType.CLAIM,
            object_id="CLM-000001",
            decision=ReviewDecision.REJECT,
            original_content_json="{}",
            review_reason="转述不忠实",
            reviewer="磁带",
        )
        assert r.decision == ReviewDecision.REJECT

    def test_invalid_decision(self):
        with pytest.raises(ValidationError):
            ReviewDecisionRecord(
                review_id="REV-000001",
                object_type=ReviewObjectType.CLAIM,
                object_id="CLM-000001",
                decision="delete",
                original_content_json="{}",
                reviewer="磁带",
            )


class TestClaimRevision:
    def test_valid_revision(self):
        r = ClaimRevision(
            revision_id="REV-000001",
            claim_id="CLM-000001",
            previous_content_json='{"source_quote":"old"}',
            new_content_json='{"source_quote":"new"}',
            changed_by="磁带",
            change_reason="修正引用错误",
        )
        assert r.changed_by == "磁带"


# ── ProcessingRun ──────────────────────────────────────

class TestProcessingRun:
    def test_valid_run(self):
        r = ProcessingRun(
            run_id="RUN-000001",
            module_name="parse_pdf",
            input_hash="d" * 64,
            status=RunStatus.STARTED,
        )
        assert r.status == RunStatus.STARTED

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            ProcessingRun(
                run_id="RUN-000001",
                module_name="parse_pdf",
                input_hash="d" * 64,
                status="complete",
            )


# ── Entity ─────────────────────────────────────────────

class TestEntity:
    def test_valid_entity(self):
        e = Entity(
            entity_id="ENT-000001",
            entity_type=EntityType.MATERIAL,
            canonical_name="HP-beta-cyclodextrin",
            display_name="HP-β-CD",
            normalised_name="hp-beta-cyclodextrin",
        )
        assert e.entity_type == EntityType.MATERIAL

    def test_invalid_entity_type(self):
        with pytest.raises(ValidationError):
            Entity(
                entity_id="ENT-000001",
                entity_type="animal",
                canonical_name="mouse",
                display_name="Mouse",
                normalised_name="mouse",
            )
