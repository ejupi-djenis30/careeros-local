import React from "react";
import { useNavigate, useLocation } from "react-router";
import { SearchForm } from "../components/SearchForm";
import { SearchService } from "../services/search";
import { useI18n } from "../i18n/useI18n";
import { describeLocalAnalysisError } from "../features/local-model/localAnalysisError";

export function NewSearchPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useI18n();
  const prefillProfile = location.state?.prefillProfile || null;
  const [isSearching, setIsSearching] = React.useState(false);

  const handleStartSearch = async (profile) => {
    setIsSearching(true);
    try {
      const result = await SearchService.start(profile);
      navigate(`/progress?pid=${result.profile_id}`);
      return { ok: true };
    } catch (error) {
      if (error.message === "UNAUTHORIZED") return { ok: false };
      const analysisError = describeLocalAnalysisError(error, t);
      if (analysisError) return { error: analysisError };
      return {
        error: t("historyPage.startFailed", {
          error: error.message || t("common.unknownError"),
        }),
      };
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="animate-slide-up w-100 h-100">
      <SearchForm onStartSearch={handleStartSearch} isLoading={isSearching} prefill={prefillProfile} />
    </div>
  );
}
