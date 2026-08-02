from __future__ import annotations

from urllib.parse import urlsplit

import httpx
import pytest

from backend.providers.configuration.client import DeclarativeJobProvider
from backend.providers.configuration.packs import bundled_provider_pack
from backend.providers.configuration.schemas import DeclarativeProviderImportEntry
from backend.providers.jobs.models import JobSearchRequest

SWISS_PACK_KEYS = [
    "job_room",
    "swissdevjobs",
    "adecco",
    "canton_bern",
    "canton_solothurn",
    "canton_lucerne",
    "fmh_doctor_jobs",
    "vmi_npo_jobs",
    "swissolar_jobs",
    "kampajobs",
    "jobs_for_change",
]

DECLARATIVE_FIXTURES = {
    "canton_bern": """
        <a class="job" href="/offene-stellen/example/bern-1">
          <h5>Data specialist</h5><p class="box-text">Public data role</p>
          <span class="inst-parent">Finance Directorate</span>
          <div class="location"><span>Bern</span></div>
        </a>
    """,
    "canton_solothurn": """
        <a class="job" href="/offene-stellen/example/so-1">
          <div class="jobTitle"><h2>Legal specialist</h2></div>
          <div class="infoLine"><div class="jobInfo"><strong>Solothurn</strong></div></div>
        </a>
    """,
    "canton_lucerne": """
        <table class="searchResult"><tbody><tr>
          <td class="position"><a href="/891537/42/pub/1/index.html">Service manager</a></td>
          <td class="department">IT Department</td><td class="workplace">Luzern</td>
        </tr></tbody></table>
    """,
    "fmh_doctor_jobs": """
        <div class="object-list"><div class="item"><div class="box">
          <div class="content"><span class="headline3">General practitioner</span>
          <div class="ort">Zürich</div><div class="tags">Internal medicine</div></div>
          <a class="absolute" href="/suche-stelle-aerzte?auftragnr=I-42"></a>
        </div></div></div>
    """,
    "vmi_npo_jobs": """
        <div class="jobs-layout"><p class="technical-title">Example Foundation</p>
          <p class="lead-medium">Fundraising lead</p><div class="link-container">
          <a href="/media/fundraising-lead.pdf">More</a></div></div>
    """,
    "swissolar_jobs": """
        <table border="1"><tbody><tr><td><strong>Solar project lead</strong></td></tr>
          <tr><td><a href="/jobs/solar-project-lead.pdf">Job description</a></td></tr>
        </tbody></table>
    """,
    "kampajobs": """
        <article class="node-job" about="/job/campaign-manager">
          <h2 class="node__title"><a href="/job/campaign-manager">Campaign manager</a></h2>
          <div class="description"><span class="recruiter-company-profile-job-organization">Example NGO</span></div>
          <div class="location">Basel</div><div class="terms">80% | Campaigning</div>
        </article>
    """,
    "jobs_for_change": """
        <li class="list-group-item" data-job="42"><a href="/jobs/social/~job42">
          <div class="row"><img alt="Example Social Foundation"><strong>Social worker</strong>
          <div class="hidden-xs">Zürich</div></div></a></li>
    """,
}


def _declarative_entries() -> dict[str, DeclarativeProviderImportEntry]:
    pack = bundled_provider_pack("careeros.switzerland.core")
    return {
        entry.configuration.key: entry
        for entry in pack.providers
        if isinstance(entry, DeclarativeProviderImportEntry)
    }


def test_switzerland_core_catalog_is_explicit_mixed_and_excludes_large_aggregators() -> None:
    pack = bundled_provider_pack("careeros.switzerland.core")
    keys = [
        entry.configuration.key
        if isinstance(entry, DeclarativeProviderImportEntry)
        else entry.key
        for entry in pack.providers
    ]
    entries = _declarative_entries()

    assert pack.version == "1.1.0"
    assert keys == SWISS_PACK_KEYS
    assert set(entries) == set(DECLARATIVE_FIXTURES)
    assert all(entry.configuration.enabled is False for entry in entries.values())
    assert all(entry.configuration.request.headers == {} for entry in entries.values())
    assert {
        urlsplit(entry.configuration.request.base_url).hostname for entry in entries.values()
    }.isdisjoint({"indeed.com", "indeed.ch", "jobs.ch", "jobup.ch"})


@pytest.mark.parametrize("provider_key", DECLARATIVE_FIXTURES)
def test_switzerland_core_declarative_selectors_extract_a_listing(provider_key: str) -> None:
    configuration = _declarative_entries()[provider_key].configuration.model_copy(
        update={"enabled": True}
    )
    provider = DeclarativeJobProvider(configuration)
    response = httpx.Response(
        200,
        content=DECLARATIVE_FIXTURES[provider_key].encode("utf-8"),
        headers={"Content-Type": "text/html; charset=utf-8"},
        request=httpx.Request("GET", configuration.request.base_url),
    )

    listings, total = provider._parse_html(  # noqa: SLF001 - pack contract regression test
        response,
        JobSearchRequest(language="de", page_size=10),
    )

    assert total is None
    assert len(listings) == 1
    assert listings[0].id
    assert listings[0].title
    assert listings[0].external_url is not None
    assert listings[0].application is not None
