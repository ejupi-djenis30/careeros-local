import pytest
from pydantic import ValidationError

from backend.resumes.schemas import ResumeDraftCreate, ResumeGenerate
from backend.resumes.templates import (
    get_template_preset,
    list_template_presets,
    resolve_template_defaults,
)


def test_all_nine_presets_defined_and_immutable():
    presets = list_template_presets()
    assert len(presets) == 9

    expected_ids = {
        "software-en",
        "cloud-platform-en",
        "swiss-software-en",
        "swiss-software-de",
        "swiss-infrastructure-en",
        "swiss-infrastructure-de",
        "logistics-de",
        "retail-de",
        "operational-de",
    }
    assert {p.id for p in presets} == expected_ids

    # 7 distinct families
    families = {p.family for p in presets}
    assert families == {
        "software",
        "cloud-platform",
        "swiss-software",
        "swiss-infrastructure",
        "logistics",
        "retail",
        "operational",
    }

    # 3 distinct layouts
    layouts = {p.layout for p in presets}
    assert layouts == {"ats", "swiss-photo", "swiss-operational"}

    # Supported locales
    locales = {p.locale for p in presets}
    assert locales == {"en", "de"}

    # Photo policies and page budgets
    for preset in presets:
        assert preset.version >= 1
        assert preset.letter_pairing is not None
        if preset.layout == "ats":
            assert preset.photo_policy == "forbidden"
            assert preset.template_kind == "ats"
            assert preset.page_budget == 2
            assert preset.preview_style["columns"] == 1
        elif preset.layout == "swiss-photo":
            assert preset.photo_policy == "optional"
            assert preset.template_kind == "photo"
            assert preset.page_budget == 2
            assert preset.preview_style["columns"] == 2
        elif preset.layout == "swiss-operational":
            assert preset.photo_policy == "optional"
            assert preset.template_kind == "photo"
            assert preset.page_budget == 1
            assert preset.preview_style["columns"] == 2

        # Headings match declared locale
        if preset.locale == "en":
            assert preset.section_headings["experience"] == "EXPERIENCE"
            assert preset.section_headings["education"] == "EDUCATION"
        elif preset.locale == "de":
            assert preset.section_headings["experience"] == "BERUFSERFAHRUNG"
            assert preset.section_headings["education"] == "AUSBILDUNG"


def test_get_template_preset_and_unknown_validation():
    preset = get_template_preset("software-en", 1)
    assert preset.id == "software-en"
    assert preset.version == 1

    with pytest.raises(ValueError, match="Unknown template preset"):
        get_template_preset("nonexistent-template")

    with pytest.raises(ValueError, match="Unknown version"):
        get_template_preset("software-en", 999)


def test_resolve_template_defaults():
    # Explicit preset ID and locale
    preset, loc = resolve_template_defaults("swiss-software-de", 1, "de")
    assert preset.id == "swiss-software-de"
    assert loc == "de"

    # Explicit preset without locale inherits preset locale
    preset, loc = resolve_template_defaults("swiss-software-de")
    assert preset.id == "swiss-software-de"
    assert loc == "de"

    # Legacy template_kind="photo" maps to swiss-software-en
    preset, loc = resolve_template_defaults(template_kind="photo")
    assert preset.id == "swiss-software-en"
    assert preset.template_kind == "photo"
    assert loc == "en"

    # Legacy template_kind="ats" maps to software-en
    preset, loc = resolve_template_defaults(template_kind="ats")
    assert preset.id == "software-en"
    assert preset.template_kind == "ats"
    assert loc == "en"

    # None maps to software-en
    preset, loc = resolve_template_defaults()
    assert preset.id == "software-en"
    assert loc == "en"


def test_preset_locale_mismatch_is_rejected_at_every_write_boundary():
    with pytest.raises(ValueError, match="locale.*does not match"):
        resolve_template_defaults("swiss-software-de", 1, "en")

    with pytest.raises(ValidationError, match="locale.*does not match"):
        ResumeDraftCreate(
            title="Inconsistent resume",
            template_id="swiss-software-de",
            template_version=1,
            locale="en",
            selected_fact_ids=["00000000-0000-4000-8000-000000000001"],
        )

    with pytest.raises(ValidationError, match="locale.*does not match"):
        ResumeGenerate(
            title="Inconsistent generated resume",
            template_id="swiss-software-de",
            template_version=1,
            locale="en",
        )


@pytest.mark.parametrize("template_version", [1, 999])
def test_template_version_without_preset_id_is_rejected_at_every_write_boundary(
    template_version,
):
    with pytest.raises(ValueError, match="version.*requires.*preset"):
        resolve_template_defaults(template_version=template_version)

    with pytest.raises(ValidationError, match="version.*requires.*preset"):
        ResumeDraftCreate(
            title="Version without preset",
            template_version=template_version,
            selected_fact_ids=["00000000-0000-4000-8000-000000000001"],
        )

    with pytest.raises(ValidationError, match="version.*requires.*preset"):
        ResumeGenerate(
            title="Generated version without preset",
            template_version=template_version,
        )


def test_explicit_empty_template_id_is_rejected_instead_of_selecting_a_default():
    with pytest.raises(ValueError, match="preset ID cannot be empty"):
        resolve_template_defaults(template_id="")

    with pytest.raises(ValidationError, match="preset ID cannot be empty"):
        ResumeGenerate(title="Empty preset", template_id="")


def test_template_catalog_api_endpoint(client, auth_headers):
    response = client.get("/api/v1/resumes/templates", headers=auth_headers)
    assert response.status_code == 200, response.text
    presets = response.json()
    assert len(presets) == 9

    by_id = {p["id"]: p for p in presets}
    assert "software-en" in by_id
    assert "operational-de" in by_id
    assert "swiss-software-en" in by_id

    operational = by_id["operational-de"]
    assert operational["layout"] == "swiss-operational"
    assert operational["page_budget"] == 1
    assert operational["locale"] == "de"
    assert operational["photo_policy"] == "optional"
    assert operational["section_headings"]["experience"] == "BERUFSERFAHRUNG"
