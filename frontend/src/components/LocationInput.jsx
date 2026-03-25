import React, { useState, useEffect, useRef } from 'react';
import { useToast } from '../context/ToastContext';

export function LocationInput({
    location,
    onLocationChange
}) {
    const { showToast } = useToast();
    const [query, setQuery] = useState(location || "");
    const [suggestions, setSuggestions] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [showSuggestions, setShowSuggestions] = useState(false);
    const wrapperRef = useRef(null);

    useEffect(() => {
        setQuery(location || "");
    }, [location]);

    useEffect(() => {
        function handleClickOutside(event) {
            if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
                setShowSuggestions(false);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, [wrapperRef]);

    const handleSearch = async (searchTerm) => {
        if (!searchTerm || searchTerm.length < 3) {
            setSuggestions([]);
            return;
        }

        setIsLoading(true);
        try {
            const response = await fetch(
                `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(searchTerm)}&countrycodes=ch&addressdetails=1&limit=5`,
                {
                    headers: {
                        "Accept-Language": "en",
                        "User-Agent": "JobHunterAI/1.0"
                    }
                }
            );
            if (!response.ok) {
                throw new Error(`Location search failed with status ${response.status}`);
            }
            const data = await response.json();
            const normalizedData = Array.isArray(data) ? data : [];

            const formattedSuggestions = normalizedData.map((item) => {
                const address = item.address || {};
                const parts = [];
                
                let street = address.road || address.pedestrian || address.highway || "";
                if (street && address.house_number) {
                    street += ` ${address.house_number}`;
                }
                if (street) parts.push(street);

                if (address.city) parts.push(address.city);
                else if (address.town) parts.push(address.town);
                else if (address.village) parts.push(address.village);
                else if (address.municipality) parts.push(address.municipality);

                if (address.state) parts.push(address.state);

                const formattedDisplayName = parts.length > 0 ? parts.join(", ") : item.display_name;

                return {
                    place_id: item.place_id,
                    display_name: formattedDisplayName,
                    lat: item.lat,
                    lon: item.lon,
                    full_name: item.display_name
                };
            });

            setSuggestions(formattedSuggestions);
            setShowSuggestions(true);
        } catch (error) {
            console.error("OSM Search Error:", error);
            showToast("Failed to fetch location suggestions. Please try again.");
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        const timer = setTimeout(() => {
            if (query !== location) {
                // When typing, we clear the locked coordinates until selection
                onLocationChange({
                    name: query,
                    lat: null,
                    lon: null
                });
                handleSearch(query);
            }
        }, 1000);
        return () => clearTimeout(timer);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [query]);

    const handleSelect = (item) => {
        setQuery(item.display_name);
        setShowSuggestions(false);
        onLocationChange({
            name: item.display_name,
            lat: parseFloat(item.lat),
            lon: parseFloat(item.lon)
        });
    };

    const handleCurrentLocation = () => {
        if (!navigator.geolocation) {
            showToast("Geolocation is not supported by your browser.");
            return;
        }

        setIsLoading(true);
        navigator.geolocation.getCurrentPosition(
            async (position) => {
                const { latitude, longitude } = position.coords;
                try {
                    const response = await fetch(
                        `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}`,
                        {
                            headers: {
                                "Accept-Language": "en",
                                "User-Agent": "JobHunterAI/1.0"
                            }
                        }
                    );
                    if (!response.ok) {
                        throw new Error(`Reverse geocoding failed with status ${response.status}`);
                    }
                    const data = await response.json();
                    const displayName = data.display_name || `Lat: ${latitude.toFixed(4)}, Lon: ${longitude.toFixed(4)}`;
                    
                    setQuery(displayName);
                    onLocationChange({
                        name: displayName,
                        lat: latitude,
                        lon: longitude
                    });
                } catch (error) {
                    console.error("Reverse Geocoding Error:", error);
                    showToast("Failed to resolve address from your current location.");
                    setQuery(`Lat: ${latitude.toFixed(4)}, Lon: ${longitude.toFixed(4)}`);
                    onLocationChange({
                        name: `Lat: ${latitude.toFixed(4)}, Lon: ${longitude.toFixed(4)}`,
                        lat: latitude,
                        lon: longitude
                    });
                } finally {
                    setIsLoading(false);
                }
            },
            (error) => {
                console.error("Geolocation Error:", error);
                showToast("Unable to retrieve your current location.");
                setIsLoading(false);
            }
        );
    };

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
