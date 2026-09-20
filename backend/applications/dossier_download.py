"""Orchestration service for application dossiers, draft bindings, and enhanced packets."""

from __future__ import annotations

import hashlib
import io
import zipfile
from typing import TYPE_CHECKING

from backend.applications.dossier_queries import DossierQueryService
from backend.applications.exceptions import (
    ApplicationNotFoundError,
    ApplicationValidationError,
)
from backend.applications.exports import (
    MAX_DOSSIER_ARTIFACT_BYTES,
    DossierBundle,
    DossierSizeError,
    build_dossier_bundle,
)
from backend.applications.models import (
    Application,
    ApplicationPacketArtifact,
)
from backend.applications.packet_storage import (
    packet_artifact_path,
    read_verified_packet_artifact,
)
from backend.core.json_safety import strict_json_loads

if TYPE_CHECKING:
    from backend.applications.service import ApplicationService

PACKET_DOWNLOAD_MEDIA_TYPES = {
    "resume.pdf": "application/pdf",
    "resume.docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "cover_letter.pdf": "application/pdf",
    "cover_letter.docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "email_draft.eml": "message/rfc822",
    "email_checklist.txt": "text/plain; charset=utf-8",
}


class DossierDownloadService(DossierQueryService):
    def dossier_artifact(
        self,
        user_id: int,
        application_id: str,
        dossier_id: str,
        filename: str,
        application_service_helper: ApplicationService,
    ) -> tuple[bytes, str, str]:
        """Download one verified declared member without extracting any files."""
        media_type = PACKET_DOWNLOAD_MEDIA_TYPES.get(filename)
        if media_type is None:
            raise ApplicationNotFoundError("Application document not found")
        bundle = self.dossier_bundle(
            user_id, application_id, dossier_id, application_service_helper
        )
        entries = [
            entry
            for entry in bundle.manifest.get("entries", [])
            if isinstance(entry, dict) and entry.get("path") == filename
        ]
        if not entries:
            raise ApplicationNotFoundError("Application document not found")
        try:
            if len(entries) != 1:
                raise ValueError("Duplicate document metadata")
            entry = entries[0]
            size = entry.get("byte_size")
            if (
                type(size) is not int
                or not 0 < size <= MAX_DOSSIER_ARTIFACT_BYTES
                or entry.get("media_type") != media_type
            ):
                raise ValueError("Invalid document metadata")
            with zipfile.ZipFile(io.BytesIO(bundle.data)) as archive:
                members = [info for info in archive.infolist() if info.filename == filename]
                if len(members) != 1 or members[0].file_size != size:
                    raise ValueError("Invalid document member")
                data = archive.read(members[0])
            digest = hashlib.sha256(data).hexdigest()
            if len(data) != size or digest != entry.get("sha256"):
                raise ValueError("Invalid document bytes")
        except Exception as exc:
            raise ApplicationValidationError("Stored document could not be verified") from exc
        return data, media_type, digest

    def dossier_bundle(
        self,
        user_id: int,
        application_id: str,
        dossier_id: str,
        application_service_helper: ApplicationService,
    ) -> DossierBundle:
        """Return downloaded dossier bundle with byte stability for both legacy and enhanced packets."""
        application = self._application(user_id, application_id)
        event = next(
            (
                item
                for item in application.events
                if item.id == dossier_id and item.event_type == "dossier_published"
            ),
            None,
        )
        if event is None:
            raise ApplicationNotFoundError("Application dossier not found")
        dossier = (event.payload or {}).get("dossier")
        if not isinstance(dossier, dict):
            raise ApplicationValidationError("Application dossier is invalid")

        schema = dossier.get("schema_version", "1.0")
        if schema in {"1.0", "2.0"}:
            return self.bundle_from_dossier(user_id, application, dossier_id, dossier)
        if schema != "3.0":
            raise ApplicationValidationError("Unsupported dossier schema")
        artifact = (
            self.db.query(ApplicationPacketArtifact)
            .filter(
                ApplicationPacketArtifact.application_id == application.id,
                ApplicationPacketArtifact.dossier_id == dossier_id,
            )
            .first()
        )
        if artifact is not None:
            try:
                if (
                    artifact.storage_path
                    != packet_artifact_path(
                        application_id=application.id, dossier_id=dossier_id, sha256=artifact.sha256
                    )
                    or artifact.media_type != "application/zip"
                ):
                    raise ValueError("Packet identity is inconsistent")
                data = read_verified_packet_artifact(
                    artifact.storage_path,
                    expected_sha256=artifact.sha256,
                    expected_size=artifact.byte_size,
                )
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    info = archive.getinfo("manifest.json")
                    if info.file_size > 256 * 1024:
                        raise ValueError("Packet manifest exceeds its limit")
                    manifest_data = archive.read(info)
                manifest = strict_json_loads(manifest_data)
                if (
                    manifest != dossier.get("manifest")
                    or hashlib.sha256(manifest_data).hexdigest() != dossier.get("manifest_sha256")
                    or manifest.get("schema_version") != "3.0"
                    or manifest.get("application_id") != application.id
                    or manifest.get("dossier_id") != dossier_id
                    or manifest.get("resume_version_id") != dossier.get("resume_version_id")
                ):
                    raise ValueError("Packet manifest identity is inconsistent")
            except Exception as exc:
                raise ApplicationValidationError(
                    "Stored packet artifact could not be read or verified"
                ) from exc
            return DossierBundle(
                data=data,
                sha256=artifact.sha256,
                manifest=dossier.get("manifest", {}),
                manifest_sha256=dossier.get("manifest_sha256", ""),
            )

        raise ApplicationValidationError("Stored packet artifact is missing")

    def bundle_from_dossier(
        self,
        user_id: int,
        application: Application,
        dossier_id: str,
        dossier: dict,
    ) -> DossierBundle:
        """Reconstruct a legacy 1.0 or 2.0 dossier bundle and verify manifest digest."""
        if dossier.get("schema_version", "1.0") not in {"1.0", "2.0"}:
            raise ApplicationValidationError("Enhanced packets require their immutable artifact")
        version = self._resume_version(user_id, dossier.get("resume_version_id"))
        if version is None:
            raise ApplicationValidationError("The dossier resume version is unavailable")
        try:
            bundle = build_dossier_bundle(
                dossier_id=dossier_id,
                version_number=dossier["version_number"],
                application_revision=dossier["application_revision"],
                application_id=application.id,
                created_at=dossier["created_at"],
                role=dossier["role"],
                resume_version_id=version.id,
                readiness=dossier["readiness"],
                cover_letter=dossier.get("cover_letter"),
                answers=dossier.get("answers") or [],
                checklist=dossier.get("checklist") or [],
                requirement_matrix=dossier.get("requirement_matrix") or [],
                evidence_catalog=(
                    dossier.get("evidence_catalog")
                    if dossier.get("schema_version") in {"2.0", "3.0"}
                    else None
                ),
                resume_artifacts=self._verified_resume_artifacts(version),
                schema_version=dossier.get("schema_version"),
            )
        except (DossierSizeError, TypeError, ValueError) as exc:
            raise ApplicationValidationError(str(exc)) from exc

        if (
            dossier.get("manifest_sha256") != bundle.manifest_sha256
            or dossier.get("manifest") != bundle.manifest
        ):
            raise ApplicationValidationError("Dossier manifest integrity check failed")
        return bundle
