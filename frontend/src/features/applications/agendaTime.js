const MAX_TIMER_DELAY_MS = 2_147_000_000;

function validInstant(value) {
    const instant = value instanceof Date ? value : new Date(value);
    return Number.isFinite(instant.getTime()) ? instant : null;
}

export function nextLocalDayEnd(now = new Date()) {
    const current = validInstant(now);
    if (!current) throw new TypeError("now must be a valid date");
    const boundary = new Date(current.getTime());
    boundary.setHours(24, 0, 0, 0);
    return boundary;
}

export function nextAgendaRefreshDelay(data, now = new Date()) {
    const current = validInstant(now);
    const generatedAt = validInstant(data?.generated_at);
    const localDayEnd = validInstant(data?.local_day_end);
    if (!current || !generatedAt || !localDayEnd) return null;

    const candidates = [localDayEnd.getTime()];
    for (const item of data?.items || []) {
        const dueAt = validInstant(item?.next_action?.due_at);
        if (dueAt && dueAt > generatedAt) candidates.push(dueAt.getTime());
    }
    const nextBoundary = Math.min(...candidates);
    return Math.min(Math.max(0, nextBoundary - current.getTime()), MAX_TIMER_DELAY_MS);
}
