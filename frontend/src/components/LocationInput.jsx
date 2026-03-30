import React, { useRef, useEffect } from 'react';
import { useLocationInput } from '../hooks/useLocationInput';

export function LocationInput({
    location,
    onLocationChange
}) {
    const {
        query,
        setQuery,
        suggestions,
        isLoading,
        showSuggestions,
        setShowSuggestions,
        handleSelect,
        handleCurrentLocation,
    } = useLocationInput(location, onLocationChange);

    const wrapperRef = useRef(null);

    useEffect(() => {
        function handleClickOutside(event) {
            if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
                setShowSuggestions(false);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, [setShowSuggestions]);

    return (
        <div className="position-relative" ref={wrapperRef}>
            <div className="position-relative">
                <input
                    type="text"
                    id="location-search"
                    name="location-search"
                    className="form-control bg-black-20 border-white-10 text-white"
                    placeholder="Search city (e.g. Zurich)..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onFocus={() => query.length >= 3 && setShowSuggestions(true)}
                    autoComplete="off"
                    style={{ paddingRight: '3rem' }}
                />

                <button
                    className="btn btn-sm btn-link text-secondary position-absolute top-50 end-0 translate-middle-y me-2 p-0 hover-text-white"
                    type="button"
                    onClick={handleCurrentLocation}
                    title="Use current location"
                    style={{ width: 32, height: 32 }}
                >
                    {isLoading ? (
                        <span className="spinner-border spinner-border-sm"></span>
                    ) : (
                        <i className="bi bi-crosshair fs-6"></i>
                    )}
                </button>
            </div>

            {/* Suggestions Dropdown */}
            {showSuggestions && suggestions.length > 0 && (
                <div className="position-absolute w-100 z-3 mt-2 animate-slide-up">
                    <div className="glass-panel overflow-hidden shadow-glow p-0" style={{ maxHeight: '250px', overflowY: 'auto', backgroundColor: '#18181b' }}>
                        <div className="list-group list-group-flush">
                            {suggestions.map((item) => (
                                <button
                                    key={item.place_id}
                                    type="button"
                                    className="list-group-item list-group-item-action bg-transparent text-light border-bottom border-white-5 px-3 py-2 text-start hover-bg-white-10 transition-colors"
                                    onClick={() => handleSelect(item)}
                                >
                                    <div className="d-flex align-items-center">
                                        <i className="bi bi-geo-alt text-primary me-3 opacity-75"></i>
                                        <div className="text-truncate">
                                            <span className="d-block small fw-bold text-white">{item.display_name.split(',')[0]}</span>
                                            <span className="d-block x-small text-secondary text-truncate">{item.display_name}</span>
                                        </div>
                                    </div>
                                </button>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
