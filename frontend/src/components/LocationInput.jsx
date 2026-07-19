import { useLocationInput } from "../hooks/useLocationInput";
import { useI18n } from "../i18n/useI18n";

export function LocationInput({ location, onLocationChange }) {
    const { t } = useI18n();
    const { query, setQuery, isLoading, handleCurrentLocation } = useLocationInput(location, onLocationChange);
    return (
        <div className="position-relative">
            <input
                type="text"
                id="location-search"
                name="location-search"
                className="form-control bg-black-20 border-white-10 text-white"
                placeholder={t("profile.locationPlaceholder")}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                autoComplete="address-level2"
                style={{ paddingRight: "3rem" }}
            />
            <button
                className="btn btn-sm btn-link text-secondary position-absolute top-50 end-0 translate-middle-y me-2 p-0 hover-text-white"
                type="button"
                onClick={handleCurrentLocation}
                title={t("location.current")}
                aria-label={t("location.current")}
                style={{ width: 32, height: 32 }}
            >
                {isLoading ? <span className="spinner-border spinner-border-sm" /> : <i className="bi bi-crosshair" />}
            </button>
        </div>
    );
}
