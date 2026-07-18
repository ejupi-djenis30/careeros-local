import { useEffect, useRef, useState } from "react";
import { useToast } from "../context/ToastContext";

/**
 * Local-only location input. It never resolves names through a remote map service.
 * Browser geolocation is optional and stores only the coordinates the user approves.
 */
export function useLocationInput(location, onLocationChange) {
    const { showToast } = useToast();
    const locationProp = location || "";
    const [input, setInput] = useState({ source: locationProp, value: locationProp });
    const [isLoading, setIsLoading] = useState(false);
    const onChangeRef = useRef(onLocationChange);

    useEffect(() => { onChangeRef.current = onLocationChange; }, [onLocationChange]);
    const query = input.source === locationProp ? input.value : locationProp;

    const setQuery = (value) => {
        setInput({ source: locationProp, value });
        // A manually edited place name can no longer be assumed to match old coordinates.
        onChangeRef.current({ name: value, lat: null, lon: null });
    };

    const handleCurrentLocation = () => {
        if (!navigator.geolocation) {
            showToast("La geolocalizzazione non è supportata dal browser.");
            return;
        }
        setIsLoading(true);
        navigator.geolocation.getCurrentPosition(
            ({ coords }) => {
                const name = `${coords.latitude.toFixed(5)}, ${coords.longitude.toFixed(5)}`;
                setInput({ source: locationProp, value: name });
                onChangeRef.current({ name, lat: coords.latitude, lon: coords.longitude });
                setIsLoading(false);
            },
            () => {
                showToast("Non è stato possibile ottenere la posizione. Puoi inserirla manualmente.");
                setIsLoading(false);
            },
            { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
        );
    };

    return { query, setQuery, isLoading, handleCurrentLocation };
}
