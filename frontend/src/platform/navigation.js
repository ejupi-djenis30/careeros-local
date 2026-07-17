import { safeExternalUrl, safeMailto } from "../lib/safeUrl";
import { isDesktopShell } from "./desktop";

function validatedExternalTarget(value) {
    if (typeof value !== "string") return null;
    if (value.startsWith("mailto:")) {
        const decoded = decodeURIComponent(value.slice("mailto:".length));
        return safeMailto(decoded);
    }
    return safeExternalUrl(value);
}

export async function openExternal(value) {
    const target = validatedExternalTarget(value);
    if (!target) throw new Error("External URL is not allowed");
    if (isDesktopShell()) {
        const { openUrl } = await import("@tauri-apps/plugin-opener");
        await openUrl(target);
        return;
    }
    window.open(target, "_blank", "noopener,noreferrer");
}

export function installExternalNavigation(root = document) {
    const handleClick = (event) => {
        if (!isDesktopShell() || event.defaultPrevented || event.button !== 0) return;
        const anchor = event.target instanceof Element ? event.target.closest("a[href]") : null;
        if (!anchor) return;
        const target = validatedExternalTarget(anchor.getAttribute("href"));
        if (!target) return;
        event.preventDefault();
        openExternal(target).catch(() => {
            window.dispatchEvent(new CustomEvent("careeros_navigation_error", {
                detail: { message: "Impossibile aprire il collegamento esterno" },
            }));
        });
    };
    root.addEventListener("click", handleClick, true);
    return () => root.removeEventListener("click", handleClick, true);
}
