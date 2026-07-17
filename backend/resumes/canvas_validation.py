from backend.resumes.canvas_schemas import ResumeCanvasDocument


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
    for section in canvas.sections:
        if not section.visible:
            continue
        for block in section.blocks:
            if not block.visible or block.kind == "identity":
                continue
            if not block.fact_ids:
                raise ValueError(
                    f"Claim block '{block.id}' requires career fact provenance before publication"
                )
            if set(block.fact_ids) - valid_fact_ids:
                raise ValueError(
                    f"Claim block '{block.id}' has invalid career fact provenance"
                )
