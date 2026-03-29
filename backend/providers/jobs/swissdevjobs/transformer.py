import logging
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from backend.providers.jobs.models import (
    ApplicationChannel,
    CompanyInfo,
    Coordinates,
    JobListing,
    JobLocation,
)

logger = logging.getLogger(__name__)


def transform_job_data(
    detail: dict[str, Any], light: dict[str, Any], source_name: str, include_raw_data: bool
) -> JobListing | None:
    """Transform JSON from SwissDevJobs into a standard JobListing model."""
    try:
        job_id = detail.get("_id") or light.get("_id")
        if not job_id:
            return None

        title = detail.get("name") or light.get("name", "Unknown Title")
        company_name = detail.get("company") or light.get("company", "Unknown Company")

        external_url = f"https://swissdevjobs.ch/jobs/{light.get('jobUrl', '')}"
        redirect_url = detail.get("redirectJobUrl") or light.get("redirectJobUrl")

        if redirect_url:
            application_url = redirect_url
        else:
            application_url = None

        contact_email = None
        if detail.get("candidateContactWay") == "Email":
            contact_email = detail.get("personEmail")

        description_html = detail.get("description", "")

        # Enrich description with tech tags if available
        techs = detail.get("technologies") or light.get("technologies", [])
        if techs:
            tech_str = ", ".join(techs)
            description_html += f"\\n\\nTechnologies: {tech_str}"

        # Location handling
        lat = detail.get("latitude") or light.get("latitude")
        lon = detail.get("longitude") or light.get("longitude")

        coordinates = None
        if lat and lon:
            coordinates = Coordinates(lat=float(lat), lon=float(lon))

        location = JobLocation(
            city=detail.get("actualCity")
            or light.get("actualCity")
            or detail.get("cityCategory")
            or "",
            postal_code=detail.get("postalCode") or light.get("postalCode"),
            country_code="CH",
            coordinates=coordinates,
        )

        company = CompanyInfo(
            name=company_name,
            website=detail.get("companyWebsiteLink") or light.get("companyWebsiteLink"),
        )

        application = ApplicationChannel(email=contact_email, form_url=application_url)

        # Date
        created_at = None
        active_from = detail.get("activeFrom") or light.get("activeFrom")
        if active_from:
            try:
                created_at = datetime.fromisoformat(active_from.replace("Z", "+00:00"))
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Invalid activeFrom for SwissDevJobs job {light.get('jobUrl')}: {e}"
                )

        return JobListing(
            id=str(job_id),
            source=source_name,
            title=title,
            descriptions=[{"language_code": "en", "title": title, "description": description_html}],
            external_url=external_url,
            company=company,
            location=location,
            application=application,
            created_at=created_at,
            raw_data=detail if include_raw_data else None,
        )
    except ValidationError as e:
        logger.warning(f"Validation error transforming job {light.get('jobUrl')}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error transforming job {light.get('jobUrl')}: {e}")
        return None
