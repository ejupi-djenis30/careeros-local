export function saveBlob({ blob, filename }) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename || "download";
    anchor.rel = "noopener";
    try {
        document.body.appendChild(anchor);
        anchor.click();
    } finally {
        anchor.remove();
        // Let the browser consume the synthetic navigation before releasing
        // the backing URL. The timer also guarantees cleanup when click throws.
        globalThis.setTimeout(() => URL.revokeObjectURL(url), 0);
    }
}
