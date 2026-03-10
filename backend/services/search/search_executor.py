import logging
import asyncio
from datetime import datetime
from backend.services.llm_service import llm_service
from backend.services.utils import haversine_distance, clean_html_tags
from backend.models import Job, ScrapedJob

logger = logging.getLogger(__name__)

async def process_job_listing(listing, profile_dict: dict, db_session) -> bool:
    """Analyse a single job listing via LLM and save it to DB."""
    # Extract description text
    desc_text = ""
    if listing.descriptions:
        desc_text = listing.descriptions[0].description

    # Enriched Metadata for deep analysis
    job_metadata = {
        "title": listing.title,
        "description": desc_text, 
        "location": listing.location.city if listing.location else "Unknown",
        "workload": f"{listing.employment.workload_min}-{listing.employment.workload_max}%" if listing.employment else "Unknown",
        "languages": [f"{s.language_code} ({s.spoken_level})" for s in listing.language_skills] if listing.language_skills else [],
        "company": listing.company.name if listing.company else "Unknown",
    }

    # Combined LLM relevance & affinity analysis
    analysis = await asyncio.to_thread(
        llm_service.analyze_job_match, job_metadata, profile_dict
    )

    # Fast fail if LLM determines title/description are fundamentally irrelevant
    if not analysis.get("relevant", True):
        logger.info(f"Skipping job due to LLM irrelevance determination: {listing.title}")
        return False

    score = analysis.get("affinity_score", 0)
    reasoning = analysis.get("affinity_analysis", "")
    worth = analysis.get("worth_applying", False)

    # Parsing fields
    company = listing.company.name if listing.company else "Unknown"
    location_str = listing.location.city if listing.location else ""
    
    workload_str = ""
    if listing.employment:
        wmin = listing.employment.workload_min
        wmax = listing.employment.workload_max
        workload_str = f"{wmin}-{wmax}%" if wmin != wmax else f"{wmin}%"

    app_url = listing.application.form_url if listing.application else None
    app_email = listing.application.email if listing.application else None

    # Fallback for JobRoom if external_url is missing
    final_external_url = listing.external_url
    if not final_external_url and listing.source == "job_room":
        final_external_url = f"https://www.job-room.ch/job-search/{listing.id}"

    pub_date = None
    if listing.publication and listing.publication.start_date:
        try:
            date_raw = listing.publication.start_date
            if "T" in date_raw:
                date_str = date_raw.replace('Z', '+00:00')
                pub_date = datetime.fromisoformat(date_str)
            else:
                pub_date = datetime.strptime(date_raw, "%Y-%m-%d")
        except (ValueError, TypeError):
            pass

    distance_km = None
    if (profile_dict.get("latitude") is not None and profile_dict.get("longitude") is not None and 
        listing.location and listing.location.coordinates):
        distance_km = round(
            haversine_distance(
                profile_dict["latitude"],
                profile_dict["longitude"],
                listing.location.coordinates.lat,
                listing.location.coordinates.lon,
            ),
            1,
        )

    # 1. UPSERT ScrapedJob + 2. CREATE Job (with rollback on error)
    try:
        scraped_job = db_session.query(ScrapedJob).filter(
            ScrapedJob.platform == listing.source,
            ScrapedJob.platform_job_id == str(listing.id)
        ).first()

        if not scraped_job:
            scraped_job = ScrapedJob(
                platform=listing.source,
                platform_job_id=str(listing.id),
                title=clean_html_tags(listing.title),
                company=company,
                description=clean_html_tags(desc_text) if desc_text else None,
                location=location_str,
                external_url=final_external_url or str(listing.id),
                application_url=app_url or None,
                application_email=app_email or None,
                workload=workload_str or None,
                publication_date=pub_date,
                raw_metadata=listing.raw_data,
                source_query=listing.title,
            )
            db_session.add(scraped_job)
            db_session.flush() # flush to get the ID for the Job

        job = Job(
            user_id=profile_dict["user_id"],
            search_profile_id=profile_dict["id"],
            scraped_job_id=scraped_job.id,
            is_scraped=True,
            affinity_score=score,
            affinity_analysis=reasoning if reasoning else None,
            worth_applying=worth,
            distance_km=distance_km,
        )

        db_session.add(job)
        db_session.commit()
        return True
    except Exception as db_err:
        logger.error(f"DB error saving job '{listing.title}': {db_err}")
        db_session.rollback()
        return False

