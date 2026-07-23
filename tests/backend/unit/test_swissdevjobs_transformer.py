from backend.providers.jobs.swissdevjobs.transformer import transform_job_data


def test_transform_job_data_logs_invalid_active_from(caplog):
    caplog.set_level("WARNING")

    listing = transform_job_data(
        detail={"_id": "1", "activeFrom": "invalid-date"},
        light={"_id": "1", "jobUrl": "python-dev"},
        source_name="swissdevjobs",
        include_raw_data=False,
    )

    assert listing is not None
    assert listing.created_at is None
    assert "Invalid activeFrom for SwissDevJobs job python-dev" in caplog.text
