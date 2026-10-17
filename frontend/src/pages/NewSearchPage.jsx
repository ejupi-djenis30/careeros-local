import { useEffect, useRef, useState } from "react";
import { useNavigate, useLocation } from "react-router";
import { SearchForm } from "../components/SearchForm";
import { SearchService } from "../services/search";
import { useI18n } from "../i18n/useI18n";
import { describeLocalAnalysisError } from "../features/local-model/localAnalysisError";

export function NewSearchPage() {
  const location = useLocation();
  return <SearchSession key={location.key} prefill={location.state?.prefillProfile || null} />;
}

function SearchSession({ prefill }) {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [isSearching, setIsSearching] = useState(false);
  const requestRef = useRef(null);

  useEffect(() => () => {
    requestRef.current?.abort();
    requestRef.current = null;
  }, []);

  const handleStartSearch = async (profile) => {
    if (requestRef.current) return { ok: false };
    const controller = new AbortController();
    requestRef.current = controller;
    const ownsRequest = () => requestRef.current === controller && !controller.signal.aborted;
    setIsSearching(true);
    try {
      const result = await SearchService.start(profile, { signal: controller.signal });
      if (!ownsRequest()) return { ok: false };
      navigate(`/progress?pid=${result.profile_id}`);
      return { ok: true };
    } catch (error) {
      if (!ownsRequest() || error.name === "AbortError" || error.message === "UNAUTHORIZED") return { ok: false };
      const analysisError = describeLocalAnalysisError(error, t);
      if (analysisError) return { error: analysisError };
      return {
        error: t("historyPage.startFailed", {
          error: error.message || t("common.unknownError"),
        }),
      };
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null;
        setIsSearching(false);
      }
    }
  };

  return (
    <div className="animate-slide-up w-100 h-100">
      <SearchForm onStartSearch={handleStartSearch} isLoading={isSearching} prefill={prefill} />
    </div>
  );
}
