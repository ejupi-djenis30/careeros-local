import React, { useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { SearchProgress } from '../components/SearchProgress';
import { useSearchContext } from '../context/SearchContext';
import { useToast } from '../context/ToastContext';
import { SearchService } from '../services/search';

export function ProgressPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const singlePid = searchParams.get('pid');

  const { searchStatuses, activeProfileIds, addProfileId, removeProfileId } = useSearchContext();
  const { showToast } = useToast();
  const [selectedProfileId, setSelectedProfileId] = React.useState(singlePid);
  const [profiles, setProfiles] = React.useState({});
  const [profilesError, setProfilesError] = React.useState('');

  useEffect(() => {
    SearchService.getProfiles()
      .then(res => {
        const mapping = {};
        (res || []).forEach(p => {
            mapping[p.id] = p.name || p.role_description || `Search #${p.id}`;
        });
        setProfiles(mapping);
        setProfilesError('');
      })
      .catch((error) => {
        console.error('Failed to load profiles for progress labels:', error);
        showToast('Failed to load profile names for active searches.');
        setProfilesError('Profile names are temporarily unavailable.');
      });
  }, [showToast]);

  useEffect(() => {
    // If we land here from an external route with a specific PID, ensure it's tracked.
    // SearchContext will expire it after PENDING_ID_TTL_MS if the server never confirms it.
    if (singlePid) {
      addProfileId(singlePid);
    }
  }, [singlePid, addProfileId]);

  const visibleProfileId = singlePid
    || (selectedProfileId && activeProfileIds.includes(String(selectedProfileId))
      ? String(selectedProfileId)
      : activeProfileIds[0] || null);

  const handleClearSearch = (profileId) => {
    const next = activeProfileIds.filter(id => id !== String(profileId));
    removeProfileId(profileId);

    // Clear search param if needed so it doesn't automatically remount
    if (searchParams.get('pid') === String(profileId)) {
      searchParams.delete('pid');
      navigate({ search: searchParams.toString() }, { replace: true });
    }

    if (next.length === 0) {
      navigate('/jobs');
    } else if (String(visibleProfileId) === String(profileId)) {
      setSelectedProfileId(next[next.length - 1]);
    }
  };

  if (activeProfileIds.length === 0) {
    return (
      <div className="animate-slide-up d-flex justify-content-center align-items-center min-h-60vh">
        <div className="glass-panel p-5 text-center max-w-480">
          <div className="rounded-circle bg-secondary bg-opacity-10 d-inline-flex align-items-center justify-content-center mb-4 sz-80">
            <i className="bi bi-cpu fs-1 text-secondary opacity-50"></i>
          </div>
          <h4 className="text-white fw-bold mb-2">No Active Searches</h4>
          <p className="text-secondary mb-4">No searches are currently running. Start a new search to find your next opportunity.</p>
          <button className="btn btn-primary px-4" onClick={() => navigate('/new')}>
            <i className="bi bi-search me-2"></i>Start a New Search
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-slide-up w-100">
      {activeProfileIds.length > 1 && (
        <div className="d-flex gap-2 mb-4 overflow-auto pb-2 custom-scrollbar">
          {activeProfileIds.map(pid => {
            const s = searchStatuses[pid];
            const isRunningTab = s && ['running', 'generating', 'searching', 'analyzing'].includes(s.state);
            const isDoneTab = s && s.state === 'done';
            const isErrorTab = s && (s.state === 'error' || s.state === 'stopped');
            const tabIcon = isRunningTab
              ? 'bi-cpu text-primary'
              : isDoneTab
                ? 'bi-check-circle-fill text-success'
                : isErrorTab
                  ? 'bi-exclamation-triangle-fill text-warning'
                  : 'bi-clock text-secondary';
            const baseName = profiles[pid] || `Search #${pid}`;
            const isActive = String(visibleProfileId) === String(pid);
            return (
              <button
                key={pid}
                className={`btn rounded-pill px-4 d-flex align-items-center gap-2 text-nowrap ${isActive ? 'btn-primary' : 'btn-outline-secondary bg-black-20 text-white'}`}
                onClick={() => setSelectedProfileId(pid)}
                title={`State: ${s?.state || 'pending'}`}
              >
                <i className={`bi ${tabIcon}`}></i>
                {baseName}
              </button>
            );
          })}
        </div>
      )}

      {profilesError && (
        <div className="alert alert-warning py-2 px-3 mb-3" role="alert">
          {profilesError}
        </div>
      )}

      {activeProfileIds.map(pid => (
        <div key={pid} className={String(visibleProfileId) === String(pid) ? 'd-block' : 'd-none'}>
          <SearchProgress
            profileId={pid}
            status={searchStatuses[pid]}
            setStatus={() => {}} // Now handled strictly by context polling
            onClear={() => handleClearSearch(pid)}
          />
        </div>
      ))}
    </div>
  );
}
