const OSM_HEADERS = {
    "Accept-Language": "en",
    "User-Agent": "JobHunterAI/1.0",
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

export const LocationService = {
    async searchLocations(term, signal) {
        const timeoutSignal = AbortSignal.timeout(5000);
        const combinedSignal = AbortSignal.any
            ? AbortSignal.any([signal, timeoutSignal])
            : signal;
        const response = await fetch(
            `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(term)}&countrycodes=ch&addressdetails=1&limit=5`,
            { signal: combinedSignal, headers: OSM_HEADERS }
        );
        if (!response.ok) throw new Error(`Location search failed: ${response.status}`);
        const data = await response.json();
        return Array.isArray(data) ? data.map(formatOsmSuggestion) : [];
    },

    async reverseGeocode(latitude, longitude) {
        const response = await fetch(
            `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}`,
            { signal: AbortSignal.timeout(5000), headers: OSM_HEADERS }
        );
        if (!response.ok) throw new Error(`Reverse geocoding failed: ${response.status}`);
        return response.json();
    },
};
