import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { SearchForm } from '../components/SearchForm';
import { useToast } from '../context/ToastContext';
import { SearchService } from '../services/search';
import { useI18n } from '../i18n/useI18n';

export function NewSearchPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { showToast } = useToast();
  const { t } = useI18n();
  const prefillProfile = location.state?.prefillProfile || null;
  const [isSearching, setIsSearching] = React.useState(false);

  const handleStartSearch = async (profile) => {
    setIsSearching(true);
    try {
      const result = await SearchService.start(profile);
      const pid = result.profile_id;
      // Navigate to progress page, passing the newly started profile id
      navigate(`/progress?pid=${pid}`);
    } catch (error) {
      if (error.message === "UNAUTHORIZED") {
         // AuthContext intercepts globally via event
         return;
      }
      showToast(t("historyPage.startFailed", { error: error.message || t("common.unknownError") }));
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="animate-slide-up w-100 h-100">
      <SearchForm
        onStartSearch={handleStartSearch}
        isLoading={isSearching}
        prefill={prefillProfile}
      />
    </div>
  );
}
