import React from 'react';
import { useNavigate } from 'react-router-dom';
import { History } from '../components/History';
import { useToast } from '../context/ToastContext';
import { SearchService } from '../services/search';

export function HistoryPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [loadingProfileId, setLoadingProfileId] = React.useState(null);

  const handleStartSearch = async (profile, overrides = {}) => {
    if (loadingProfileId !== null) return; // prevent double-fire while any request is in-flight
    const pid = profile.id;
    setLoadingProfileId(pid);
    try {
      const result = await SearchService.start({ ...profile, ...overrides });
      navigate(`/progress?pid=${result.profile_id}`);
    } catch (error) {
      if (error.message === 'UNAUTHORIZED') return; // intercepted globally by auth layer
      if (error.message?.includes('409') || error.status === 409) {
        showToast({ messageKey: "historyPage.alreadyRunning" }, "warning");
      } else {
        showToast({
          messageKey: "historyPage.startFailed",
          variables: { error: error.message || { messageKey: "common.unknownError" } },
        });
      }
      console.error("Failed to start search:", error);
    } finally {
      setLoadingProfileId(null);
    }
  };

  const handleUseAsTemplate = (profile) => {
    // Strip id and metadata so a fresh profile is created on submit
    const { id: _id, created_at: _created_at, last_scheduled_run: _last_scheduled_run, ...templateData } = profile;
    navigate('/new', { state: { prefillProfile: templateData } });
  };

  const handleSaveAsSchedule = async (profile) => {
    try {
      await SearchService.toggleSchedule(profile.id, true, profile.schedule_interval_hours || 24);
      showToast({ messageKey: "historyPage.scheduleAdded" }, "success");
    } catch (error) {
      showToast({
        messageKey: "historyPage.scheduleFailed",
        variables: { error: error.message || { messageKey: "common.unknownError" } },
      });
    }
  };

  return (
    <div className="animate-slide-up">
      <History
        onStartSearch={handleStartSearch}
        onStartSearchWithOptions={handleStartSearch}
        onUseAsTemplate={handleUseAsTemplate}
        onSaveAsSchedule={handleSaveAsSchedule}
        loadingProfileId={loadingProfileId}
      />
    </div>
  );
}
