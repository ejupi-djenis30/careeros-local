import { useLocationInput } from "../hooks/useLocationInput";

export function LocationInput({ location, onLocationChange }) {
    const { query, setQuery, isLoading, handleCurrentLocation } = useLocationInput(location, onLocationChange);
    return (
        <div className="position-relative">
            <input
                type="text"
                id="location-search"
                name="location-search"
                className="form-control bg-black-20 border-white-10 text-white"
                placeholder="Città o area (testo libero)"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                autoComplete="address-level2"
                style={{ paddingRight: "3rem" }}
            />
            <button
                className="btn btn-sm btn-link text-secondary position-absolute top-50 end-0 translate-middle-y me-2 p-0 hover-text-white"
                type="button"
                onClick={handleCurrentLocation}
                title="Usa coordinate correnti senza geocoding esterno"
                aria-label="Usa posizione corrente"
                style={{ width: 32, height: 32 }}
            >
                {isLoading ? <span className="spinner-border spinner-border-sm" /> : <i className="bi bi-crosshair" />}
            </button>
        </div>
    );
}
