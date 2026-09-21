"""Compatibility facade for focused dossier preparation, publication and download services."""

from backend.applications.dossier_download import DossierDownloadService
from backend.applications.dossier_drafts import DossierDraftService
from backend.applications.dossier_publication import DossierPublicationService


class ApplicationDossierService(
    DossierDraftService, DossierPublicationService, DossierDownloadService
):
    pass
