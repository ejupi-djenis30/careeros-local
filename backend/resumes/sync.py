from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from backend.resumes.canvas_schemas import CanvasBlock, CanvasSection, ResumeCanvasDocument
from backend.resumes.schemas import ResumeSyncSection


@dataclass(frozen=True)
class CanvasSyncPlan:
    sections: list[ResumeSyncSection]
    preserved_manual_fields: list[str]


def _fact_ids(section: CanvasSection | None) -> list[str]:
    if section is None:
        return []
    return list(dict.fromkeys(fact_id for block in section.blocks for fact_id in block.fact_ids))


def _by_fact(section: CanvasSection | None) -> dict[str, CanvasBlock]:
    if section is None:
        return {}
    return {
        block.fact_ids[0]: block
        for block in section.blocks
        if block.fact_ids and block.kind == "fact"
    }


def plan_sync(
    current: ResumeCanvasDocument,
    generated: ResumeCanvasDocument,
) -> CanvasSyncPlan:
    current_by_kind = {section.kind: section for section in current.sections}
    generated_by_kind = {section.kind: section for section in generated.sections}
    kinds = list(dict.fromkeys([*current_by_kind, *generated_by_kind]))
    changes: list[ResumeSyncSection] = []
    preserved: list[str] = []
    for kind in kinds:
        old = current_by_kind.get(kind)
        new = generated_by_kind.get(kind)
        old_ids, new_ids = _fact_ids(old), _fact_ids(new)
        old_blocks, new_blocks = _by_fact(old), _by_fact(new)
        changed: list[str] = []
        conflicts: list[str] = []
        for fact_id in set(old_blocks) & set(new_blocks):
            old_block, new_block = old_blocks[fact_id], new_blocks[fact_id]
            if old_block.content != new_block.content:
                changed.append(fact_id)
            for field in old_block.manual_fields:
                preserved.append(f"{kind}:{fact_id}:{field}")
                if getattr(old_block.content, field) != getattr(new_block.content, field):
                    conflicts.append(f"{fact_id}:{field}")
        if kind == "summary" and old and new and old.blocks and new.blocks:
            if old.blocks[0].content != new.blocks[0].content:
                changed.extend(new_ids or old_ids)
            for field in old.blocks[0].manual_fields:
                preserved.append(f"summary:{field}")
                if getattr(old.blocks[0].content, field) != getattr(new.blocks[0].content, field):
                    conflicts.append(f"summary:{field}")
        added = [fact_id for fact_id in new_ids if fact_id not in old_ids]
        removed = [fact_id for fact_id in old_ids if fact_id not in new_ids]
        if added or removed or changed or conflicts or (old is None) != (new is None):
            changes.append(
                ResumeSyncSection(
                    kind=kind,
                    added_fact_ids=added,
                    removed_fact_ids=removed,
                    changed_fact_ids=list(dict.fromkeys(changed)),
                    conflicts=list(dict.fromkeys(conflicts)),
                )
            )
    return CanvasSyncPlan(sections=changes, preserved_manual_fields=list(dict.fromkeys(preserved)))


def _merge_block(old: CanvasBlock, new: CanvasBlock) -> CanvasBlock:
    data = new.model_dump(mode="json")
    old_content = old.content.model_dump(mode="json")
    for field in old.manual_fields:
        data["content"][field] = old_content[field]
    data["manual_fields"] = list(old.manual_fields)
    data["visible"] = old.visible
    data["layout"] = old.layout.model_dump(mode="json")
    return CanvasBlock.model_validate(data)


def _merge_section(old: CanvasSection | None, new: CanvasSection | None) -> CanvasSection | None:
    if new is None:
        if old is None:
            return None
        ungrounded = [
            block for block in old.blocks if block.kind == "fact" and not block.fact_ids
        ]
        return old.model_copy(update={"blocks": ungrounded}) if ungrounded else None
    if old is None:
        return new
    new_by_fact = _by_fact(new)
    merged_by_fact = {
        fact_id: _merge_block(old_block, new_by_fact[fact_id])
        for fact_id, old_block in _by_fact(old).items()
        if fact_id in new_by_fact
    }
    ordered: list[CanvasBlock] = []
    used: set[str] = set()
    for old_block in old.blocks:
        fact_id = old_block.fact_ids[0] if old_block.fact_ids else None
        if old_block.kind == "fact" and not fact_id:
            ordered.append(old_block)
        elif fact_id and fact_id in merged_by_fact:
            ordered.append(merged_by_fact[fact_id])
            used.add(fact_id)
        elif old_block.kind in {"identity", "summary"} and new.blocks:
            ordered.append(_merge_block(old_block, new.blocks[0]))
            used.update(new.blocks[0].fact_ids)
    for block in new.blocks:
        fact_id = block.fact_ids[0] if block.fact_ids else None
        if fact_id not in used and block.kind == "fact":
            ordered.append(block)
    if not ordered:
        ordered = list(new.blocks)
    return CanvasSection(
        id=old.id,
        kind=new.kind,
        title=old.title,
        visible=old.visible,
        page_break_before=old.page_break_before,
        blocks=ordered,
    )


def apply_sync(
    current: ResumeCanvasDocument,
    generated: ResumeCanvasDocument,
    selected_kinds: set[str],
    *,
    reset: bool = False,
) -> ResumeCanvasDocument:
    if reset:
        return ResumeCanvasDocument.model_validate(generated.model_dump(mode="json"))
    new_by_kind = {section.kind: section for section in generated.sections}
    sections: list[CanvasSection] = []
    consumed: set[str] = set()
    for old in current.sections:
        kind = old.kind
        if kind in selected_kinds:
            merged = _merge_section(old, new_by_kind.get(kind))
            if merged:
                sections.append(merged)
        else:
            sections.append(old)
        consumed.add(kind)
    for new in generated.sections:
        if new.kind in selected_kinds and new.kind not in consumed:
            sections.append(new)
    return ResumeCanvasDocument(
        schema_version=current.schema_version,
        sections=deepcopy(sections),
        style=current.style,
    )


def selected_ids(canvas: ResumeCanvasDocument) -> list[str]:
    return list(
        dict.fromkeys(
            fact_id
            for section in canvas.sections
            for block in section.blocks
            for fact_id in block.fact_ids
        )
    )
