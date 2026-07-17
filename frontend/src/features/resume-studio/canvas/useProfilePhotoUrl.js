import { useEffect, useState } from "react";
import { CareerService } from "../../../services/career";

export function useProfilePhotoUrl(assetId) {
    const [loaded, setLoaded] = useState({ assetId: null, url: null });
    useEffect(() => {
        if (!assetId) return undefined;
        let active = true;
        let objectUrl = null;
        CareerService.getPhoto(assetId).then(({ blob }) => {
            if (!active) return;
            objectUrl = URL.createObjectURL(blob);
            setLoaded({ assetId, url: objectUrl });
        }).catch(() => {
            if (active) setLoaded({ assetId, url: null });
        });
        return () => {
            active = false;
            if (objectUrl) URL.revokeObjectURL(objectUrl);
        };
    }, [assetId]);
    return loaded.assetId === assetId ? loaded.url : null;
}
