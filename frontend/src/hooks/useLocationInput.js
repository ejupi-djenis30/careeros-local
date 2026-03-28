import { useState, useEffect, useRef } from 'react';
import { useToast } from '../context/ToastContext';

const OSM_HEADERS = {
    "Accept-Language": "en",
    "User-Agent": "JobHunterAI/1.0"
};

function formatOsmSuggestion(item) {
    const address = item.address || {};
    const parts = [];

    let street = address.road || address.pedestrian || address.highway || "";
    if (street && address.house_number) street += ` ${address.house_number}`;
    if (street) parts.push(street);

    const city = address.city || address.town || address.village || address.municipality;
    if (city) parts.push(city);
    if (address.state) parts.push(address.state);

    return {
        place_id: item.place_id,
        display_name: parts.length > 0 ? parts.join(", ") : item.display_name,
        lat: item.lat,
        lon: item.lon,
    };
}

/**
 * Encapsulates all state, search, and geolocation logic for the LocationInput component.
 */
export function useLocationInput(location, onLocationChange) {
    const { showToast } = useToast();
    const [query, setQuery] = useState(location || "");
    const [suggestions, setSuggestions] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [showSuggestions, setShowSuggestions] = useState(false);

    const onLocationChangeRef = useRef(onLocationChange);
    useEffect(() => { onLocationChangeRef.current = onLocationChange; }, [onLocationChange]);
    const locationRef = useRef(location);
    useEffect(() => { locationRef.current = location; }, [location]);

    useEffect(() => {
        setQuery(location || "");
    }, [location]);

    const fetchSuggestions = async (searchTerm, signal) => {
        if (!searchTerm || searchTerm.length < 3) {
            setSuggestions([]);
            return;
        }
        setIsLoading(true);
        try {
            const timeoutSignal = AbortSignal.timeout(5000);
            const combinedSignal = AbortSignal.any
                ? AbortSignal.any([signal, timeoutSignal])
                : signal;
            const response = await fetch(
                `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(searchTerm)}&countrycodes=ch&addressdetails=1&limit=5`,
                { signal: combinedSignal, headers: OSM_HEADERS }
            );
            if (!response.ok) throw new Error(`Location search failed: ${response.status}`);
            const data = await response.json();
            setSuggestions(Array.isArray(data) ? data.map(formatOsmSuggestion) : []);
            setShowSuggestions(true);
        } catch (error) {
            if (error.name === 'AbortError') return;
            console.error("OSM Search Error:", error);
            showToast("Failed to fetch location suggestions. Please try again.");
        } finally {
            setIsLoading(false);
        }
    };

    // Debounce input changes
    useEffect(() => {
        const abortController = new AbortController();
        const timer = setTimeout(() => {
            if (query !== locationRef.current) {
                onLocationChangeRef.current({ name: query, lat: null, lon: null });
                fetchSuggestions(query, abortController.signal);
            }
        }, 1000);
        return () => {
            clearTimeout(timer);
            abortController.abort();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [query]);

    const handleSelect = (item) => {
        setQuery(item.display_name);
        setShowSuggestions(false);
        onLocationChangeRef.current({
            name: item.display_name,
            lat: parseFloat(item.lat),
            lon: parseFloat(item.lon),
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
                        { signal: AbortSignal.timeout(5000), headers: OSM_HEADERS }
                    );
                    if (!response.ok) throw new Error(`Reverse geocoding failed: ${response.status}`);
                    const data = await response.json();
                    const displayName = data.display_name || `Lat: ${latitude.toFixed(4)}, Lon: ${longitude.toFixed(4)}`;
                    setQuery(displayName);
                    onLocationChangeRef.current({ name: displayName, lat: latitude, lon: longitude });
                } catch (error) {
                    console.error("Reverse Geocoding Error:", error);
                    showToast("Failed to resolve address from your current location.");
                    const fallback = `Lat: ${latitude.toFixed(4)}, Lon: ${longitude.toFixed(4)}`;
                    setQuery(fallback);
                    onLocationChangeRef.current({ name: fallback, lat: latitude, lon: longitude });
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

    return {
        query,
        setQuery,
        suggestions,
        isLoading,
        showSuggestions,
        setShowSuggestions,
        handleSelect,
        handleCurrentLocation,
    };
}
