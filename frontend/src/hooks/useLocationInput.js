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

    // Tracks the last coordinates explicitly confirmed by the user (via handleSelect or
    // handleCurrentLocation). Preserved while the user is mid-typing so the parent form
    // doesn't temporarily enter an invalid state during the debounce window.
    const lastConfirmedRef = useRef({ name: location || '', lat: null, lon: null });

    // Monotonically increasing request ID used to discard stale suggestion responses.
    const requestIdRef = useRef(0);

    useEffect(() => {
        // Sync internal query AND confirmed name when the location prop changes externally
        // (e.g. parent resets the field or loads a saved profile). Only update
        // lastConfirmedRef when the incoming location is actually a different value.
        if (location !== lastConfirmedRef.current.name) {
            lastConfirmedRef.current = { name: location || '', lat: null, lon: null };
        }
        setQuery(location || '');
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
        // Field cleared: immediately drop coordinates and hide suggestions.
        if (!query) {
            lastConfirmedRef.current = { name: '', lat: null, lon: null };
            onLocationChangeRef.current({ name: '', lat: null, lon: null });
            setSuggestions([]);
            setShowSuggestions(false);
            return undefined;
        }

        // Query matches the last confirmed selection — no search needed.
        if (query === lastConfirmedRef.current.name) return undefined;

        const myId = ++requestIdRef.current;
        const abortController = new AbortController();
        const timer = setTimeout(async () => {
            // Notify parent with current text but preserve confirmed coords so the form
            // doesn't enter temporarily invalid state during the debounce window.
            onLocationChangeRef.current({
                name: query,
                lat: lastConfirmedRef.current.lat,
                lon: lastConfirmedRef.current.lon,
            });
            await fetchSuggestions(query, abortController.signal);
            // Discard stale suggestions if a newer request superseded this one.
            if (myId !== requestIdRef.current) {
                setSuggestions([]);
                setShowSuggestions(false);
            }
        }, 800);
        return () => {
            clearTimeout(timer);
            abortController.abort();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [query]);

    const handleSelect = (item) => {
        const confirmed = {
            name: item.display_name,
            lat: parseFloat(item.lat),
            lon: parseFloat(item.lon),
        };
        lastConfirmedRef.current = confirmed;
        setQuery(item.display_name);
        setShowSuggestions(false);
        onLocationChangeRef.current(confirmed);
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
                    const confirmed = { name: displayName, lat: latitude, lon: longitude };
                    lastConfirmedRef.current = confirmed;
                    setQuery(displayName);
                    onLocationChangeRef.current(confirmed);
                } catch (error) {
                    console.error("Reverse Geocoding Error:", error);
                    showToast("Failed to resolve address from your current location.");
                    const fallback = `Lat: ${latitude.toFixed(4)}, Lon: ${longitude.toFixed(4)}`;
                    const confirmedFallback = { name: fallback, lat: latitude, lon: longitude };
                    lastConfirmedRef.current = confirmedFallback;
                    setQuery(fallback);
                    onLocationChangeRef.current(confirmedFallback);
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
