"""Import every persistence model exactly once for SQLAlchemy metadata discovery."""

from backend.ai import models as ai_models
from backend.applications import models as application_models
from backend.automation import models as automation_models
from backend.career import coach_models as coach_models
from backend.career import models as career_models
from backend.models import auth_session as auth_session_models
from backend.models import job as job_models
from backend.models import search_profile as search_profile_models
from backend.models import user as user_models
from backend.providers.configuration import models as provider_configuration_models
from backend.resumes import models as resume_models
from backend.workflows import models as workflow_models

__all__ = [
    "ai_models",
    "application_models",
    "automation_models",
    "career_models",
    "coach_models",
    "auth_session_models",
    "job_models",
    "provider_configuration_models",
    "resume_models",
    "search_profile_models",
    "user_models",
    "workflow_models",
]
