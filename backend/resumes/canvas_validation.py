from backend.resumes.canvas_schemas import ResumeCanvasDocument


def build_claim_evidence_map(canvas: ResumeCanvasDocument) -> dict[str, list[str]]:
    return {
        block.id: list(block.fact_ids)
        for section in canvas.sections
        if section.visible
        for block in section.blocks
        if block.visible and block.kind in {"summary", "fact"} and block.fact_ids
    }


def validate_canvas_references(
    canvas: ResumeCanvasDocument,
    selected_fact_ids: set[str],
) -> None:
    for section in canvas.sections:
        for block in section.blocks:
            missing = set(block.fact_ids) - selected_fact_ids
            if missing:
                raise ValueError(
                    "Canvas blocks must reference selected career facts: "
                    + ", ".join(sorted(missing))
                )


def validate_publishable_canvas(
    canvas: ResumeCanvasDocument,
    valid_fact_ids: set[str],
) -> None:
    visible_fact_blocks = 0
    for section in canvas.sections:
        if not section.visible:
            continue
        for block in section.blocks:
            if not block.visible or block.kind == "identity":
                continue
            if block.kind == "fact":
                visible_fact_blocks += 1
            if not block.fact_ids:
                raise ValueError(
                    f"Claim block '{block.id}' requires career fact provenance before publication"
                )
            if block.kind == "fact" and not block.content.title.strip():
                raise ValueError(f"Claim block '{block.id}' requires a title before publication")
            if set(block.fact_ids) - valid_fact_ids:
                raise ValueError(
                    f"Claim block '{block.id}' has invalid career fact provenance"
                )
    identity = next(
        (section for section in canvas.sections if section.kind == "identity" and section.visible),
        None,
    )
    if identity is None or not any(
        block.visible and block.content.title.strip() for block in identity.blocks
    ):
        raise ValueError("A publishable resume requires a visible identity name")
    if visible_fact_blocks == 0:
        raise ValueError("A publishable resume requires at least one visible career fact")
