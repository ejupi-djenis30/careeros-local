from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from backend.main import app
from backend.api.deps import get_current_user_id, get_db, get_job_service, get_profile_service
from backend.services.search_service import SearchService

client = TestClient(app, raise_server_exceptions=False)

def test_jobs_routes_full():
    app.dependency_overrides[get_current_user_id] = lambda: 1
    mock_job_service = MagicMock()
    mock_job_service.create_job.return_value = {"id": 1, "title": "new", "company": "comp", "external_url": "url", "description": "desc"}
    mock_job_service.update_job.return_value = {"id": 1, "title": "updated"}
    mock_job_service.get_jobs_by_user.return_value = {"items": [], "total": 0, "page": 1, "size": 20, "pages": 0, "total_applied": 0, "avg_score": 0}
    app.dependency_overrides[get_job_service] = lambda: mock_job_service
    
    # 1. read_jobs without filters (lines 30-41)
    client.get("/api/v1/jobs/")
    mock_job_service.get_jobs_by_user.assert_called_once()
    
    # 2. create_job (line 50)
    client.post("/api/v1/jobs/", json={"title": "test", "company": "test", "external_url": "http://test", "provider_id": "1", "description": "d"})
    mock_job_service.create_job.assert_called_once()
    
    # 3. update_job (line 60)
    client.patch("/api/v1/jobs/1", json={"applied": True})
    mock_job_service.update_job.assert_called_once()

    app.dependency_overrides.clear()

def test_schedules_routes_full():
    app.dependency_overrides[get_current_user_id] = lambda: 1
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    with patch("backend.api.routes.schedules.get_scheduler") as mock_get_scheduler, \
         patch("backend.api.routes.schedules.get_all_schedules", return_value=[{"id": 1}, {"id": 2}]):
        
        # Scheduler running
        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        mock_get_scheduler.return_value = mock_scheduler
        
        res_status = client.get("/api/v1/schedules/status")
        assert res_status.json()["running"] is True
        assert res_status.json()["jobs_scheduled"] == 2
        
        # Scheduler None
        mock_get_scheduler.return_value = None
        res_status2 = client.get("/api/v1/schedules/status")
        assert res_status2.json()["running"] is False
        assert res_status2.json()["jobs_scheduled"] == 0
        
        # List schedules
        res_list = client.get("/api/v1/schedules/")
        assert len(res_list.json()) == 2
        
    app.dependency_overrides.clear()

def test_profiles_routes_full():
    app.dependency_overrides[get_current_user_id] = lambda: 1
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    mock_profile_service = MagicMock()
    mock_profile_service.get_profiles_by_user.return_value = [{"id": 1, "name": "hi", "role_description": "dev", "location_filter": "us", "created_at": "2024-01-01T00:00:00"}]
    mock_profile_service.create_profile.return_value = {"id": 1, "name": "hi", "role_description": "dev", "location_filter": "us", "created_at": "2024-01-01T00:00:00"}
    app.dependency_overrides[get_profile_service] = lambda: mock_profile_service
    
    # 1. get_profiles
    client.get("/api/v1/profiles/")
    mock_profile_service.get_profiles_by_user.assert_called_once()
    
    # 2. create_profile
    client.post("/api/v1/profiles/", json={"role_description": "dev", "location_filter": "us", "name": "hi"})
    mock_profile_service.create_profile.assert_called_once()

    
    # 4. toggle_schedule
    client.patch("/api/v1/profiles/1/schedule", json={"enabled": True, "interval_hours": 12})
    mock_profile_service.toggle_schedule.assert_called_once()
    app.dependency_overrides.clear()

def test_search_routes_full():
    app.dependency_overrides[get_current_user_id] = lambda: 1
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    # upload-cv success
    with patch("backend.api.routes.search.extract_text_from_file", return_value="CV content"):
        import io
        files = {"file": ("test.pdf", io.BytesIO(b"dump"), "application/pdf")}
        res = client.post("/api/v1/search/upload-cv", files=files)
        assert res.json()["text"] == "CV content"
        
    # start_search Profile ID provided, but wrong user
    with patch("backend.api.routes.search.ProfileRepository") as MockRepo:
        mock_repo = MagicMock()
        mock_repo.get.return_value = MagicMock(user_id=2)
        MockRepo.return_value = mock_repo
        
        payload = {"id": 1, "name": "Test", "role_description": "dev", "location_filter": "test"}
        res = client.post("/api/v1/search/start", json=payload)
        assert res.status_code == 403
        
        # start_search Profile ID provided, user authorized (line 66)
        with patch("fastapi.BackgroundTasks.add_task") as mock_add_task, \
             patch("backend.api.routes.search.cancel_task"):
            mock_repo.get.return_value = MagicMock(user_id=1) # Authorized
            mock_repo.update.return_value = MagicMock(id=1)
            res_auth = client.post("/api/v1/search/start", json=payload)
            assert res_auth.status_code == 200
        
    # stop_search full
    with patch("backend.api.routes.search.ProfileRepository") as MockRepo, \
         patch("backend.api.routes.search.update_status"), \
         patch("backend.api.routes.search.cancel_task"):
        mock_repo = MagicMock()
        # Unauthorized
        mock_repo.get.return_value = MagicMock(user_id=2)
        MockRepo.return_value = mock_repo
        res = client.post("/api/v1/search/stop/1")
        assert res.status_code == 403
        
        # Authorized
        prof = MagicMock(user_id=1, is_stopped=False)
        mock_repo.get.return_value = prof
        res2 = client.post("/api/v1/search/stop/1")
        assert res2.status_code == 200
        
    # status_all
    with patch("backend.api.routes.search.get_all_statuses", return_value={}):
        client.get("/api/v1/search/status/all")
        
    # status individual valid
    with patch("backend.api.routes.search.ProfileRepository") as MockRepo, \
         patch("backend.api.routes.search.get_status", return_value={"state": "running"}):
        mock_repo = MagicMock()
        mock_repo.get.return_value = MagicMock(user_id=1)
        MockRepo.return_value = mock_repo
        res = client.get("/api/v1/search/status/1")
        assert res.status_code == 200
        
    app.dependency_overrides.clear()

def test_run_search_background_wrapper():
    from backend.api.routes.search import start_search
    import asyncio
    
    bg_tasks = MagicMock()
    mock_app_db = MagicMock()
    mock_request = MagicMock()
    
    # We will invoke start_search directly to capture the internal async wrapper
    class FakeStartReq:
        id = None
        name: str = "test"
        role_description: str = "dev"
        location_filter: str = "us"
        search_strategy: str = "broad"
        max_queries: int = 5
        posted_within_days: int = 7
        max_distance: int = 50
        schedule_interval_hours: int = 24
        force_regenerate_cv_summary = False
        force_regenerate_queries = False
        def model_dump(self, exclude_unset=True):
            return {
                "id": self.id, "name": self.name, "role_description": self.role_description,
                "location_filter": self.location_filter, "search_strategy": self.search_strategy,
                "max_queries": self.max_queries, "posted_within_days": self.posted_within_days, "max_distance": self.max_distance, "schedule_interval_hours": self.schedule_interval_hours,
                "force_regenerate_cv_summary": False, "force_regenerate_queries": False
            }
            
    with patch("backend.api.routes.search.ProfileRepository") as MockRepo, \
         patch("backend.api.routes.search.cancel_task"), \
         patch("backend.api.routes.search.SessionLocal") as mock_session_local, \
         patch("backend.api.routes.search.get_search_service") as mock_get_svc:
         
        mock_repo = MagicMock()
        mock_repo.create.return_value = MagicMock(id=99)
        MockRepo.return_value = mock_repo
        
        mock_fresh_db = MagicMock()
        mock_session_local.return_value = mock_fresh_db
        
        mock_svc = MagicMock()
        async def mock_run(*args, **kwargs):
            return None
        mock_svc.run_search = mock_run
        mock_get_svc.return_value = mock_svc
        
        asyncio.run(start_search(mock_request, FakeStartReq(), bg_tasks, mock_app_db, 1))
        
        # Check bg task added
        bg_func = bg_tasks.add_task.call_args[0][0]
        arg_id = bg_tasks.add_task.call_args[0][1]
        
        # Execute the wrapper manually
        bg_args = bg_tasks.add_task.call_args[0]
        asyncio.run(bg_func(*bg_args[1:]))
        
        mock_session_local.assert_called()
        mock_fresh_db.close.assert_called()

def test_deps_full():
    from backend.api.deps import get_current_user_id, get_job_service, get_profile_service
    from fastapi import HTTPException
    import pytest
    
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    
    with patch("backend.api.deps.decode_access_token", return_value={"sub": "missing_user"}):
        with pytest.raises(HTTPException) as exc:
            get_current_user_id(token="dummy", db=mock_db)
        assert exc.value.status_code == 401
        assert "User not found" in str(exc.value.detail)
        
    # Evaluate job/profile service wrappers
    with patch("backend.services.job_service.get_job_service") as mock_js:
        get_job_service(mock_db)
        mock_js.assert_called_with(mock_db)
        
    with patch("backend.services.profile_service.get_profile_service") as mock_ps:
        get_profile_service(mock_db)
        mock_ps.assert_called_with(mock_db)

    # test success
    mock_user = MagicMock(id=5)
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user
    with patch("backend.api.deps.decode_access_token", return_value={"sub": "exist_user"}):
        res_id = get_current_user_id(token="dummy", db=mock_db)
        assert res_id == 5
