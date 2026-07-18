"""Seed a fictional, judge-friendly CareerOS Local workspace through its loopback API."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from email.message import Message
from typing import IO, Any, Protocol

API_PREFIX = "/api/v1"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_USERNAME = "ada_demo"
DEFAULT_PASSWORD = "AdaDemo2026!"
DEMO_NAME = "Ada Lovelace"
DEMO_RESUME_TITLE = "Ada Lovelace — ATS Demo"
DEMO_JOB_TITLE = "Local Systems Architect"
DEMO_JOB_COMPANY = "Analytical Engines Cooperative"

PROFILE_PAYLOAD: dict[str, Any] = {
    "expected_revision": 0,
    "display_name": DEMO_NAME,
    "headline": "Principal Local Systems Engineer",
    "summary": (
        "Builds dependable, privacy-preserving software and helps engineering teams turn "
        "ambiguous problems into testable systems."
    ),
    "email": "ada@example.test",
    "phone": "+41 79 000 00 00",
    "location": {"city": "Zurich", "country": "CH"},
    "website": "https://ada.example.test",
    "preferences": {
        "workload_min": 80,
        "workload_max": 100,
        "preferred_languages": ["en"],
    },
    "facts": [
        {
            "fact_type": "experience",
            "position": 0,
            "verification_status": "confirmed",
            "payload": {
                "role": "Principal Engineer",
                "organization": "Analytical Engines Cooperative",
                "employment_type": "permanent",
                "industry": "Software",
                "work_mode": "hybrid",
                "location": "Zurich",
                "start_date": "2021-01-01",
                "current": True,
                "description": "Leads delivery of private, local-first developer tools.",
                "responsibilities": [
                    "Set technical direction",
                    "Turn product risks into automated checks",
                    "Mentor engineers",
                ],
                "achievements": [
                    "Shipped a deterministic local workflow with documented recovery paths."
                ],
                "technologies": ["Python", "React", "Rust", "SQLite"],
                "skills": ["Architecture", "Privacy engineering", "Technical leadership"],
                "team_size": 8,
            },
        },
        {
            "fact_type": "education",
            "position": 1,
            "verification_status": "confirmed",
            "payload": {
                "institution": "University of London",
                "qualification": "BSc Mathematics",
                "field": "Mathematics",
                "start_date": "2012-09-01",
                "end_date": "2015-06-30",
                "coursework": ["Algorithms", "Statistics"],
            },
        },
        {
            "fact_type": "skill",
            "position": 2,
            "verification_status": "confirmed",
            "payload": {
                "name": "Python",
                "category": "Engineering",
                "level": "expert",
                "years": 10,
                "last_used_date": "2026-07-01",
            },
        },
    ],
    "goals": [
        {
            "name": "Local-first engineering leadership",
            "is_primary": True,
            "payload": {
                "status": "active",
                "priority": 1,
                "target_roles": ["Staff Engineer", "Principal Engineer"],
                "target_industries": ["Software"],
                "target_locations": ["Switzerland"],
                "target_seniority": ["staff", "lead"],
                "work_modes": ["hybrid", "remote"],
                "contract_types": ["permanent"],
                "must_haves": ["Technical leadership", "Privacy-respecting product"],
                "deal_breakers": ["Mandatory relocation"],
            },
        }
    ],
}

APPLICATION_PAYLOAD: dict[str, Any] = {
    "manual_job": {
        "title": DEMO_JOB_TITLE,
        "company": DEMO_JOB_COMPANY,
        "description": (
            "Fictional role for demonstrating CareerOS Local's application workflow."
        ),
        "location": "Zurich",
        "external_url": "https://example.test/jobs/careeros-demo",
        "workload": "80–100%",
    },
    "initial_stage": "preparing",
    "note": "Fictional judge demo; no external application was sent.",
}


class SeedError(RuntimeError):
    """An actionable, secret-free demo seed failure."""


@dataclass(frozen=True)
class ApiResult:
    status: int
    value: Any = None


@dataclass(frozen=True)
class SeedSummary:
    account: str
    profile: str
    ats_resume: str
    application: str

    def render(self) -> str:
        return (
            "CareerOS demo ready: "
            f"account={self.account}, profile={self.profile}, "
            f"ats_resume={self.ats_resume}, application={self.application}."
        )


class JsonApi(Protocol):
    def request_json(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        form: Mapping[str, str] | None = None,
        token: str | None = None,
        allowed_statuses: Collection[int] = (200,),
    ) -> ApiResult: ...


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> urllib.request.Request | None:
        del req, fp, code, msg, headers, newurl
        return None


def normalize_base_url(value: str) -> str:
    """Return a canonical loopback origin or reject the URL."""
    candidate = value.strip()
    try:
        parsed = urllib.parse.urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise SeedError("The API base URL is invalid") from exc

    if parsed.scheme not in {"http", "https"}:
        raise SeedError("The API base URL must use HTTP or HTTPS")
    if not parsed.netloc or parsed.hostname is None:
        raise SeedError("The API base URL must include a loopback host")
    if parsed.username is not None or parsed.password is not None:
        raise SeedError("The API base URL must not contain credentials")
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise SeedError("The API base URL must be an origin without a path, query, or fragment")

    hostname = parsed.hostname.casefold()
    if hostname != "localhost":
        if "%" in hostname:
            raise SeedError("Scoped IPv6 addresses are not accepted as API loopback hosts")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError as exc:
            raise SeedError("The API base URL must use localhost or a loopback IP address") from exc
        if not address.is_loopback:
            raise SeedError("Refusing to send demo credentials to a non-loopback API")
        hostname = address.compressed

    host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = f"{host}:{port}" if port is not None else host
    return urllib.parse.urlunsplit((parsed.scheme.casefold(), netloc, "", "", ""))


class ApiClient:
    def __init__(self, base_url: str, *, timeout: float = 20.0) -> None:
        self.base_url = normalize_base_url(base_url)
        self.timeout = timeout
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirectHandler(),
        )

    def request_json(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        form: Mapping[str, str] | None = None,
        token: str | None = None,
        allowed_statuses: Collection[int] = (200,),
    ) -> ApiResult:
        if payload is not None and form is not None:
            raise ValueError("A request cannot contain both JSON and form data")
        if not path.startswith("/") or "://" in path:
            raise ValueError("API paths must be root-relative")

        body: bytes | None = None
        headers = {
            "Accept": "application/json",
            "User-Agent": "careeros-local-demo-seed/1",
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif form is not None:
            body = urllib.parse.urlencode(form).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"

        request = urllib.request.Request(
            f"{self.base_url}{API_PREFIX}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                status = int(response.status)
                response_body = response.read()
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            exc.close()
            if status in allowed_statuses:
                return ApiResult(status=status)
            raise SeedError(f"{method} {path} failed with HTTP {status}") from exc
        except (OSError, urllib.error.URLError) as exc:
            raise SeedError(f"Could not reach the local CareerOS API at {self.base_url}") from exc

        if status not in allowed_statuses:
            raise SeedError(f"{method} {path} returned unexpected HTTP {status}")
        if not response_body:
            return ApiResult(status=status)
        try:
            value = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SeedError(f"{method} {path} returned invalid JSON") from exc
        return ApiResult(status=status, value=value)


def validate_credentials(username: str, password: str) -> None:
    if not 3 <= len(username) <= 50 or re.fullmatch(r"[A-Za-z0-9_]+", username) is None:
        raise SeedError("The username must be 3–50 alphanumeric or underscore characters")
    if len(password) < 8 or re.search(r"[A-Z]", password) is None or re.search(r"\d", password) is None:
        raise SeedError("The password must be at least 8 characters with a capital and a digit")


def _object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SeedError(f"The local API returned an invalid {context} response")
    return value


def _array(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise SeedError(f"The local API returned an invalid {context} response")
    return value


def _access_token(value: Any) -> str:
    token = _object(value, "authentication").get("access_token")
    if not isinstance(token, str) or not token:
        raise SeedError("The local API returned an invalid authentication response")
    return token


def ensure_account(api: JsonApi, username: str, password: str) -> tuple[str, str]:
    registered = api.request_json(
        "POST",
        "/auth/register",
        payload={"username": username, "password": password},
        allowed_statuses=(200, 400),
    )
    if registered.status == 200:
        return _access_token(registered.value), "created"

    logged_in = api.request_json(
        "POST",
        "/auth/login",
        form={"username": username, "password": password},
        allowed_statuses=(200, 401),
    )
    if logged_in.status == 401:
        raise SeedError("The demo account exists, but the supplied password was rejected")
    return _access_token(logged_in.value), "reused"


def _profile_ready(profile: Mapping[str, Any]) -> bool:
    if profile.get("display_name") != DEMO_NAME:
        return False
    facts = profile.get("facts")
    if not isinstance(facts, list):
        return False
    confirmed_types = {
        item.get("fact_type")
        for item in facts
        if isinstance(item, dict) and item.get("verification_status") == "confirmed"
    }
    return {"experience", "education", "skill"}.issubset(confirmed_types)


def ensure_profile(api: JsonApi, token: str) -> tuple[dict[str, Any], str]:
    current = api.request_json(
        "GET", "/career-profile", token=token, allowed_statuses=(200, 404)
    )
    if current.status == 200:
        profile = _object(current.value, "career profile")
        if not _profile_ready(profile):
            raise SeedError(
                "The account already has a different or incomplete profile; use another username"
            )
        return profile, "reused"

    created = api.request_json(
        "PUT",
        "/career-profile",
        payload=PROFILE_PAYLOAD,
        token=token,
        allowed_statuses=(200,),
    )
    profile = _object(created.value, "career profile")
    if not _profile_ready(profile):
        raise SeedError("The local API did not persist the verified Ada demo profile")
    return profile, "created"


def ensure_resume(api: JsonApi, token: str) -> str:
    resumes = _array(
        api.request_json("GET", "/resumes", token=token, allowed_statuses=(200,)).value,
        "resume list",
    )
    matching = [
        item
        for item in resumes
        if isinstance(item, dict) and item.get("title") == DEMO_RESUME_TITLE
    ]
    if matching:
        if any(item.get("template_kind") == "ats" for item in matching):
            return "reused"
        raise SeedError("A non-ATS resume already uses the reserved demo title")

    created = _object(
        api.request_json(
            "POST",
            "/resumes/generate",
            payload={"title": DEMO_RESUME_TITLE, "template_kind": "ats"},
            token=token,
            allowed_statuses=(201,),
        ).value,
        "resume",
    )
    if created.get("title") != DEMO_RESUME_TITLE or created.get("template_kind") != "ats":
        raise SeedError("The local API did not create the requested ATS resume")
    return "created"


def ensure_application(api: JsonApi, token: str) -> str:
    applications = _array(
        api.request_json(
            "GET", "/applications?limit=500", token=token, allowed_statuses=(200,)
        ).value,
        "application list",
    )
    if any(
        isinstance(item, dict)
        and item.get("title") == DEMO_JOB_TITLE
        and item.get("company") == DEMO_JOB_COMPANY
        for item in applications
    ):
        return "reused"

    created = _object(
        api.request_json(
            "POST",
            "/applications",
            payload=APPLICATION_PAYLOAD,
            token=token,
            allowed_statuses=(201,),
        ).value,
        "application",
    )
    snapshot = created.get("job_snapshot")
    if not isinstance(snapshot, dict) or (
        snapshot.get("title"), snapshot.get("company")
    ) != (DEMO_JOB_TITLE, DEMO_JOB_COMPANY):
        raise SeedError("The local API did not create the requested demo application")
    return "created"


def seed_demo(api: JsonApi, username: str, password: str) -> SeedSummary:
    validate_credentials(username, password)
    token, account = ensure_account(api, username, password)
    _profile, profile = ensure_profile(api, token)
    ats_resume = ensure_resume(api, token)
    application = ensure_application(api, token)
    return SeedSummary(
        account=account,
        profile=profile,
        ats_resume=ats_resume,
        application=application,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Populate a fictional Ada workspace through a loopback CareerOS API."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Loopback server origin")
    parser.add_argument("--username", default=DEFAULT_USERNAME, help="Local demo account name")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Local demo account password")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        api = ApiClient(arguments.base_url)
        summary = seed_demo(api, arguments.username, arguments.password)
    except SeedError as exc:
        print(f"CareerOS demo seed failed: {exc}", file=sys.stderr)
        return 1
    print(summary.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
