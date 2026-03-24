import React from 'react';
import { useNavigate } from 'react-router-dom';
import { History } from '../components/History';
import { SearchService } from '../services/search';

export function HistoryPage() {
  const navigate = useNavigate();

  const handleStartSearch = async (profile, overrides = {}) => {
    try {
      const result = await SearchService.start({ ...profile, ...overrides });
      const pid = result.profile_id;
      navigate(`/progress?pid=${pid}`);
    } catch (error) {
       // 401 intercepted globally
      console.error("Failed to start search:", error);
    }
  };

  const handleUseAsTemplate = (profile) => {
    // Strip id and metadata so a fresh profile is created on submit
    const { id, created_at, last_scheduled_run, ...templateData } = profile;
    navigate('/new', { state: { prefillProfile: templateData } });
  };

  const handleSaveAsSchedule = async (profile) => {
    try {
      await SearchService.toggleSchedule(profile.id, true, profile.schedule_interval_hours || 24);
      alert("Search profile added to schedules!");
    } catch (error) {
      alert("Failed to save schedule: " + error.message);
    }
  };

  return (
    <div className="animate-slide-up">
      <History
        onStartSearch={handleStartSearch}
        onStartSearchWithOptions={handleStartSearch}
        onUseAsTemplate={handleUseAsTemplate}
        onSaveAsSchedule={handleSaveAsSchedule}
      />
    </div>
  );
}
