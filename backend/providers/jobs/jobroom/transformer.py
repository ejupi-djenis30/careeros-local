from datetime import datetime
from typing import Any

from backend.providers.jobs.models import (
    ApplicationChannel,
    CompanyInfo,
    ContactInfo,
    Coordinates,
    EmploymentDetails,
    JobDescription,
    JobListing,
    JobLocation,
    LanguageSkill,
    Occupation,
    PublicationInfo,
)


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert value to int."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def transform_job_data(raw: dict[str, Any], source_name: str, include_raw_data: bool = False) -> JobListing:
    """Transform job-room.ch response to generalized JobListing."""
    job = raw.get("jobAdvertisement", raw)
    content = job.get("jobContent", {})

    # Extract descriptions (multilingual)
    descriptions = []
    for desc in content.get("jobDescriptions", []):
        descriptions.append(
            JobDescription(
                language_code=desc.get("languageIsoCode", "en"),
                title=desc.get("title", ""),
                description=desc.get("description", ""),
            )
        )

    title = ""
    if descriptions:
        title = descriptions[0].title

    # Extract company info
    company_data = content.get("company", {})
    company = CompanyInfo(
        name=company_data.get("name"),
        street=company_data.get("street"),
        house_number=company_data.get("houseNumber"),
        postal_code=company_data.get("postalCode"),
        city=company_data.get("city"),
        country_code=company_data.get("countryIsoCode"),
        phone=company_data.get("phone"),
        email=company_data.get("email"),
        website=company_data.get("website"),
        is_agency=company_data.get("surrogate", False),
    )

    # Extract location
    location_data = content.get("location") or {}
    coords_data = location_data.get("coordinates") or {}
    coordinates = None
    if coords_data.get("lat") and coords_data.get("lon"):
        try:
            coordinates = Coordinates(
                lat=float(coords_data["lat"]),
                lon=float(coords_data["lon"]),
            )
        except (ValueError, TypeError):
            pass

    location = JobLocation(
        city=location_data.get("city", ""),
        postal_code=location_data.get("postalCode"),
        canton_code=location_data.get("cantonCode"),
        region_code=location_data.get("regionCode"),
        communal_code=location_data.get("communalCode"),
        country_code=location_data.get("countryIsoCode", "CH"),
        coordinates=coordinates,
        remarks=location_data.get("remarks"),
    )

    # Extract employment details
    emp_data = content.get("employment", {})
    employment = EmploymentDetails(
        start_date=emp_data.get("startDate"),
        end_date=emp_data.get("endDate"),
        is_permanent=emp_data.get("permanent", True),
        is_immediate=emp_data.get("immediately", False),
        is_short_employment=emp_data.get("shortEmployment", False),
        workload_min=safe_int(emp_data.get("workloadPercentageMin"), 100),
        workload_max=safe_int(emp_data.get("workloadPercentageMax"), 100),
        work_forms=emp_data.get("workForms", []),
    )

    # Extract occupations
    occupations = []
    for occ in content.get("occupations", []):
        occupations.append(
            Occupation(
                avam_code=occ.get("avamOccupationCode", ""),
                work_experience=occ.get("workExperience"),
                education_code=occ.get("educationCode"),
                qualification_code=occ.get("qualificationCode"),
            )
        )

    # Extract language skills
    language_skills = []
    for ls in content.get("languageSkills", []):
        language_skills.append(
            LanguageSkill(
                language_code=ls.get("languageIsoCode", ""),
                spoken_level=ls.get("spokenLevel"),
                written_level=ls.get("writtenLevel"),
            )
        )

    # Extract contact info
    contact_data = content.get("publicContact", {})
    contact = (
        ContactInfo(
            salutation=contact_data.get("salutation"),
            first_name=contact_data.get("firstName"),
            last_name=contact_data.get("lastName"),
            phone=contact_data.get("phone"),
            email=contact_data.get("email"),
        )
        if contact_data
        else None
    )

    # Extract application channel
    apply_data = content.get("applyChannel") or {}

    post_address = apply_data.get("postAddress") or apply_data.get("rawPostAddress")
    if isinstance(post_address, dict):
        addr_parts = []
        if post_address.get("name"):
            addr_parts.append(post_address["name"])
        if post_address.get("street"):
            street = post_address["street"]
            if post_address.get("houseNumber"):
                street += f" {post_address['houseNumber']}"
            addr_parts.append(street)
        if post_address.get("postalCode") or post_address.get("city"):
            addr_parts.append(
                f"{post_address.get('postalCode', '')} {post_address.get('city', '')}".strip()
            )
        if post_address.get("countryIsoCode") and post_address["countryIsoCode"] != "CH":
            addr_parts.append(post_address["countryIsoCode"])
        post_address = ", ".join(addr_parts) if addr_parts else None

    form_url = apply_data.get("formUrl") or content.get("externalUrl")

    if apply_data or form_url:
        application = ApplicationChannel(
            email=apply_data.get("emailAddress"),
            phone=apply_data.get("phoneNumber"),
            form_url=form_url,
            post_address=post_address,
            additional_info=apply_data.get("additionalInfo"),
        )
    else:
        application = None

    # Extract publication info
    pub_data = job.get("publication", {})
    publication = (
        PublicationInfo(
            start_date=pub_data.get("startDate", ""),
            end_date=pub_data.get("endDate", ""),
            public_display=pub_data.get("publicDisplay", True),
            eures_display=pub_data.get("euresDisplay", False),
            company_anonymous=pub_data.get("companyAnonymous", False),
            restricted_display=pub_data.get("restrictedDisplay", False),
        )
        if pub_data
        else None
    )

    # Parse timestamps
    created_at = None
    if job.get("createdTime"):
        try:
            created_at = datetime.fromisoformat(
                job["createdTime"].replace("Z", "+00:00")
            )
        except (ValueError, TypeError):
            pass

    updated_at = None
    if job.get("updatedTime"):
        try:
            updated_at = datetime.fromisoformat(
                job["updatedTime"].replace("Z", "+00:00")
            )
        except (ValueError, TypeError):
            pass

    return JobListing(
        id=job.get("id", ""),
        source=source_name,
        external_reference=job.get("externalReference"),
        stellennummer_egov=job.get("stellennummerEgov"),
        stellennummer_avam=job.get("stellennummerAvam"),
        title=title,
        descriptions=descriptions,
        external_url=f"https://www.job-room.ch/job-search/{job.get('id')}" if job.get("id") else None,
        company=company,
        location=location,
        number_of_positions=safe_int(content.get("numberOfJobs"), 1),
        employment=employment,
        occupations=occupations,
        language_skills=language_skills,
        contact=contact,
        application=application,
        publication=publication,
        created_at=created_at,
        updated_at=updated_at,
        status=job.get("status"),
        reporting_obligation=job.get("reportingObligation", False),
        reporting_obligation_end_date=job.get("reportingObligationEndDate"),
        raw_data=raw if include_raw_data else None,
    )
