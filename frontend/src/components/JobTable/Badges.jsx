import React from "react";

export function ScoreBadge({ score }) {
    let colorClass = "badge-secondary";
    let icon = "bi-dash";
    
    if (score >= 85) {
        colorClass = "badge-success";
        icon = "bi-check-lg";
    } else if (score >= 70) {
        colorClass = "badge-warning";
        icon = "bi-exclamation";
    }

    return (
        <span className={`badge-pill ${colorClass} d-inline-flex align-items-center gap-1`}>
            <i className={`bi ${icon}`} style={{ fontSize: '0.9em' }}></i>
            {score}%
        </span>
    );
}

export function DistanceBadge({ km }) {
    if (km == null) return <span className="text-secondary small opacity-50">—</span>;
    let colorClass = "text-secondary";
    if (km <= 15) colorClass = "text-success";
    else if (km <= 40) colorClass = "text-info";

    return (
        <span className={`small fw-medium ${colorClass} d-inline-flex align-items-center bg-black-20 px-2 py-1 rounded`}>
            <i className="bi bi-geo-alt me-1 opacity-75"></i>{parseFloat(Number(km).toFixed(2))}km
        </span>
    );
}
