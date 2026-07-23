from typing import Any

from backend.search.normalization.listings import (
    coerce_int,
    compute_prescore,
    normalized_text_token,
    semantic_skills_score,
)


def _job_value(job: dict[str, Any], field: str):
    value = job.get(field)
    return value if value is not None else job.get(f"normalized_{field}")


def deterministic_job_prefilter(job: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Build model-free pre-filter signals; never represent them as completed analysis."""
    score = round(compute_prescore(job, profile), 1)
    job_skills = [str(item) for item in (_job_value(job, "required_skills") or []) if item]
    profile_skills = [
        str(item)
        for item in (
            profile.get("intent_skills")
            or profile.get("skills")
            or profile.get("normalized_skills")
            or []
        )
        if item
    ]
    profile_skill_tokens = {normalized_text_token(item) for item in profile_skills}
    matched_skills = sorted(
        item for item in job_skills if normalized_text_token(item) in profile_skill_tokens
    )
    missing_skills = sorted(item for item in job_skills if item not in matched_skills)
    skill_score = round(semantic_skills_score(job_skills, profile_skills) * 100, 1)
    if not job_skills:
        skill_score = 50.0

    job_exp_min = coerce_int(_job_value(job, "experience_min_years"), None)
    job_exp_max = coerce_int(_job_value(job, "experience_max_years"), None)
    profile_exp = coerce_int(
        profile.get("experience_years") or profile.get("years_of_experience"), None
    )
    if profile_exp is None or (job_exp_min is None and job_exp_max is None):
        experience_score = 50.0
    elif job_exp_min is not None and profile_exp < job_exp_min:
        experience_score = max(0.0, 100.0 - (job_exp_min - profile_exp) * 20.0)
    elif job_exp_max is not None and profile_exp > job_exp_max:
        experience_score = 75.0
    else:
        experience_score = 100.0

    job_domain = str(_job_value(job, "domain") or "general").lower()
    profile_domain = str(profile.get("intent_domain") or profile.get("domain") or "general").lower()
    intent_score = (
        50.0
        if "general" in {job_domain, profile_domain}
        else (100.0 if job_domain == profile_domain else 0.0)
    )

    required_languages = _job_value(job, "required_languages") or []
    profile_languages = profile.get("languages") or profile.get("normalized_languages") or []
    available_codes = {
        str(item.get("code") or item.get("language") or "").lower()
        if isinstance(item, dict)
        else str(item).lower()
        for item in profile_languages
    }
    required_codes = {
        str(item.get("code") or item.get("language") or "").lower()
        if isinstance(item, dict)
        else str(item).lower()
        for item in required_languages
    }
    required_codes.discard("")
    if not required_codes:
        language_score = 50.0
    else:
        language_score = round(len(required_codes & available_codes) / len(required_codes) * 100, 1)

    missing_languages = sorted(required_codes - available_codes)
    return {
        "kind": "deterministic_prefilter",
        "prescore": score,
        "signals": {
            "skills": skill_score,
            "experience": experience_score,
            "intent": intent_score,
            "language": language_score,
        },
        "matched_skills": matched_skills,
        "unconfirmed_skills": missing_skills,
        "unconfirmed_languages": missing_languages,
    }
