"""
Transformer for Adecco API data.
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import ValidationError

from backend.providers.jobs.models import (
    ApplicationChannel,
    CompanyInfo,
    ContactInfo,
    EmploymentDetails,
    JobDescription,
    JobListing,
    JobLocation,
)

logger = logging.getLogger(__name__)

def parse_date(date_str: str | None) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        # e.g., 2025-12-30T14:19:33Z
        clean_str = date_str.replace("Z", "+00:00")
        return datetime.fromisoformat(clean_str)
    except ValueError:
        return None

def transform_job_data(
    light_job: Dict[str, Any],
    detail_job: Optional[Dict[str, Any]],
    source_name: str,
    include_raw_data: bool = False
) -> JobListing | None:
    """
    Transforms Adecco API JSON dictionaries into a standardized JobListing.
    """
    try:
        # Detail data is the primary truth for description, but light_job has list metadata
        primary_source = detail_job if detail_job else light_job

        job_id = light_job.get("jobId", "unknown")

        # 1. Basic Info
        title = primary_source.get("jobName") or light_job.get("jobTitle") or "Unknown Title"
        external_ref = light_job.get("externalReference")

        # 2. Company Info
        # Adecco often hides the company or acts as the agency.
        company_name = primary_source.get("companyName")
        company = CompanyInfo(
            name=company_name,
            is_agency=True  # Adecco is an agency
        ) if company_name else CompanyInfo(name="Adecco", is_agency=True)

        # 3. Location
        country_raw = light_job.get("countryId", "CH")
        country_map = {"CHE": "CH", "DEU": "DE", "AUT": "AT", "FRA": "FR"}
        country_normalized = country_map.get(country_raw, country_raw)

        location = JobLocation(
            city=light_job.get("cityName", ""),
            canton_code=light_job.get("stateName"),
            country_code=country_normalized,
        )

        # 4. Employment Details
        contract_type_id = light_job.get("contractTypeId", "")
        is_permanent = contract_type_id == "PERM"

        work_forms = []
        if light_job.get("isRemote"):
            work_forms.append("remote")

        start_date = primary_source.get("startDate")

        # Workload mapping
        emp_type_id = light_job.get("employmentTypeId", "")
        if emp_type_id == "FULLTIME":
            wmin, wmax = 80, 100
        elif emp_type_id == "PARTTIME":
            wmin, wmax = 20, 80
        else:
            wmin, wmax = 0, 100

        # Override with exact hours if provided and sensible
        min_hours = light_job.get("workMinHours", 0)
        max_hours = light_job.get("workMaxHours", 0)
        if min_hours > 0 and max_hours > 0 and max_hours <= 100:
            wmin, wmax = min_hours, max_hours

        employment = EmploymentDetails(
            is_permanent=is_permanent,
            start_date=start_date,
            work_forms=work_forms,
            workload_min=wmin,
            workload_max=wmax
        )

        # 5. Descriptions
        descriptions = []
        desc_html = primary_source.get("jobDescription")
        if desc_html:
            lang_code_str = light_job.get("language", "en-US")
            lang = lang_code_str.split("-")[0] if "-" in lang_code_str else "en"

            descriptions.append(
                JobDescription(
                    language_code=lang,
                    title="Job Description",
                    description=desc_html
                )
            )

        # 6. Contact and Application
        contact = None
        recruiter = primary_source.get("recruiterName") or light_job.get("recruiterName")
        if recruiter:
            parts = recruiter.split(" ", 1)
            first = parts[0]
            last = parts[1] if len(parts) > 1 else None

            contact = ContactInfo(
                first_name=first,
                last_name=last,
                email=primary_source.get("recruiterEmail")
            )

        application = None
        apply_uri = primary_source.get("applyUri") or light_job.get("applyUri")
        if apply_uri:
            application = ApplicationChannel(form_url=apply_uri)

        # Dates
        created_at = parse_date(light_job.get("postedDate") or light_job.get("jobCreationDate"))

        raw_data = None
        if include_raw_data:
            raw_data = {
                "light": light_job,
                "detail": detail_job
            }

        return JobListing(
            id=job_id,
            source=source_name,
            external_reference=external_ref,
            title=title,
            descriptions=descriptions,
            external_url=apply_uri,
            company=company,
            location=location,
            employment=employment,
            contact=contact,
            application=application,
            created_at=created_at,
            raw_data=raw_data
        )
    except ValidationError as e:
        logger.warning(f"Validation error transforming Adecco job {job_id}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error transforming Adecco job {job_id}: {e}")
        return None
