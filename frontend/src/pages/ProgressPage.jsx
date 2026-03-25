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
  const [visibleProfileId, setVisibleProfileId] = React.useState(singlePid);
  const [profiles, setProfiles] = React.useState({});

  useEffect(() => {
    SearchService.getProfiles()
      .then(res => {
        const mapping = {};
        (res || []).forEach(p => {
            mapping[p.id] = p.name || p.role_description || `Search #${p.id}`;
        });
        setProfiles(mapping);
      })
      .catch((error) => {
        console.error('Failed to load profiles for progress labels:', error);
        showToast('Failed to load profile names for active searches.');
      });
  }, [showToast]);

  useEffect(() => {
    // If we land here from an external route with a specific PID, ensure it's tracked
    if (singlePid) {
      addProfileId(singlePid);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (!visibleProfileId) setVisibleProfileId(singlePid);
    } else if (activeProfileIds.length > 0 && !visibleProfileId) {
      setVisibleProfileId(activeProfileIds[0]);
    }
  }, [singlePid, addProfileId, visibleProfileId, activeProfileIds]);

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
      setVisibleProfileId(next[next.length - 1]);
    }
  };

  const handleSearchStateChange = () => {
    // Optional Hook for when search finishes
  };

  if (activeProfileIds.length === 0) {
    return (
      <div className="d-flex justify-content-center align-items-center h-100 text-white-50">
        No active searches in progress.
      </div>
    );
  }

  return (
    <div className="animate-slide-up w-100">
      {activeProfileIds.length > 1 && (
        <div className="d-flex gap-2 mb-4 overflow-auto pb-2 custom-scrollbar">
          {activeProfileIds.map(pid => {
            const s = searchStatuses[pid];
            const isRunning = s && ['running', 'generating', 'searching', 'analyzing'].includes(s.state);
            const baseName = profiles[pid] || `Search #${pid}`;
            const label = s ? (isRunning ? `${baseName} (Active)` : `${baseName} (${s.state})`) : baseName;
            return (
              <button 
                key={pid}
                className={`btn rounded-pill px-4 whitespace-nowrap ${String(visibleProfileId) === String(pid) ? 'btn-primary' : 'btn-outline-secondary bg-black-20 text-white'}`}
                onClick={() => setVisibleProfileId(pid)}
              >
                {label}
              </button>
            );
          })}
        </div>
      )}

      {activeProfileIds.map(pid => (
        <div key={pid} style={{ display: String(visibleProfileId) === String(pid) ? 'block' : 'none' }}>
          <SearchProgress
            profileId={pid}
            status={searchStatuses[pid]}
            setStatus={() => {}} // Now handled strictly by context polling
            onStateChange={handleSearchStateChange}
            onClear={() => handleClearSearch(pid)}
          />
        </div>
      ))}
    </div>
  );
}
