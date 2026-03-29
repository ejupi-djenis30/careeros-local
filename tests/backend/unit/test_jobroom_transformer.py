from backend.providers.jobs.jobroom.transformer import safe_int, transform_job_data


def test_safe_int():
    assert safe_int("100") == 100
    assert safe_int(None) == 0
    assert safe_int("abc", default=50) == 50


def test_transform_job_data_minimal():
    raw = {
        "id": "1",
        "jobContent": {
            "jobDescriptions": [
                {"languageIsoCode": "de", "title": "Test Job", "description": "Desc"}
            ]
        },
    }
    listing = transform_job_data(raw, "job_room")
    assert listing.id == "1"
    assert listing.title == "Test Job"
    assert listing.external_url == "https://www.job-room.ch/job-search/1"


def test_transform_job_data_complex_address():
    raw = {
        "jobAdvertisement": {
            "id": "2",
            "jobContent": {
                "applyChannel": {
                    "postAddress": {
                        "name": "Company Name",
                        "street": "Bahnhofstr",
                        "houseNumber": "1",
                        "postalCode": "8000",
                        "city": "Zurich",
                        "countryIsoCode": "CH",
                    }
                }
            },
        }
    }
    listing = transform_job_data(raw, "job_room")
    assert "Company Name, Bahnhofstr 1, 8000 Zurich" in listing.application.post_address


def test_transform_job_data_no_descriptions():
    raw = {"id": "3", "jobContent": {}}
    listing = transform_job_data(raw, "job_room")
    assert listing.title == ""
    assert listing.descriptions == []


def test_transform_job_data_invalid_coords_and_dates():
    raw = {
        "id": "4",
        "createdTime": "invalid-date",
        "jobContent": {
            "location": {"coordinates": {"lat": "invalid", "lon": "9.0"}},
            "employment": {"workloadPercentageMin": "invalid"},
        },
    }
    listing = transform_job_data(raw, "job_room")
    assert listing.created_at is None
    assert listing.location.coordinates is None
    assert listing.employment.workload_min == 100  # default


def test_transform_job_data_logs_invalid_values(caplog):
    caplog.set_level("WARNING")
    raw = {
        "id": "5",
        "createdTime": "invalid-created",
        "updatedTime": "invalid-updated",
        "jobContent": {
            "location": {"coordinates": {"lat": "x", "lon": "y"}},
        },
    }

    listing = transform_job_data(raw, "job_room")

    assert listing.created_at is None
    assert listing.updated_at is None
    assert listing.location.coordinates is None
    assert "Invalid job-room coordinates" in caplog.text
    assert "Invalid job-room createdTime" in caplog.text
    assert "Invalid job-room updatedTime" in caplog.text
