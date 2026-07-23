from uuid import uuid4

import pytest

from backend.resumes.canvas_schemas import (
    CanvasBlock,
    CanvasContent,
    CanvasSection,
    ResumeCanvasDocument,
)
from backend.resumes.canvas_validation import (
    build_claim_evidence_map,
    validate_publishable_canvas,
)


def _canvas(*, title: str = "Evidence-backed outcome", visible: bool = True):
    fact_id = str(uuid4())
    return fact_id, ResumeCanvasDocument(
        sections=[
            CanvasSection(
                id="identity",
                kind="identity",
                title="IDENTITY",
                blocks=[
                    CanvasBlock(
                        id="identity-main",
                        kind="identity",
                        content=CanvasContent(title="Mira Vale"),
                    )
                ],
            ),
            CanvasSection(
                id="achievement",
                kind="achievement",
                title="ACHIEVEMENTS",
                blocks=[
                    CanvasBlock(
                        id="claim-one",
                        kind="fact",
                        fact_ids=[fact_id],
                        visible=visible,
                        content=CanvasContent(title=title),
                    )
                ],
            ),
        ]
    )


def test_claim_evidence_map_contains_only_visible_publishable_claims():
    fact_id, canvas = _canvas()
    assert build_claim_evidence_map(canvas) == {"claim-one": [fact_id]}
    _, hidden = _canvas(visible=False)
    assert build_claim_evidence_map(hidden) == {}


def test_publication_rejects_blank_visible_claims_but_allows_hidden_drafts():
    fact_id, canvas = _canvas(title="")
    with pytest.raises(ValueError, match="title"):
        validate_publishable_canvas(canvas, {fact_id})

    hidden_id, hidden = _canvas(title="", visible=False)
    visible_id = str(uuid4())
    hidden.sections[1].blocks.append(
        CanvasBlock(
            id="claim-visible",
            kind="fact",
            fact_ids=[visible_id],
            content=CanvasContent(title="Verified visible claim"),
        )
    )
    validate_publishable_canvas(hidden, {hidden_id, visible_id})


def test_canvas_v1_is_upgraded_and_block_geometry_is_bounded():
    _, canvas = _canvas()
    legacy = canvas.model_dump(mode="json")
    legacy["schema_version"] = 1
    assert ResumeCanvasDocument.model_validate(legacy).schema_version == 2
    legacy["sections"][1]["blocks"][0]["layout"]["spacing_before_pt"] = 25
    with pytest.raises(ValueError, match="less than or equal to 24"):
        ResumeCanvasDocument.model_validate(legacy)
