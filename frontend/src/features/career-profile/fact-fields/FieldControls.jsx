import { useState } from "react";

export function Input({ label, ...props }) {
    return <label className="field-stack"><span>{label}</span><input className="form-control" {...props} /></label>;
}

export function Select({ label, children, ...props }) {
    return <label className="field-stack"><span>{label}</span><select className="form-select" {...props}>{children}</select></label>;
}

export function Textarea({ label, ...props }) {
    return <label className="field-stack"><span>{label}</span><textarea className="form-control" rows="4" {...props} /></label>;
}

export function Lines({ label, value, onChange }) {
    const serialized = (value || []).join("\n");
    const [draft, setDraft] = useState(serialized);
    return <Textarea label={label} value={draft} onChange={(event) => {
        const raw = event.target.value;
        setDraft(raw);
        onChange(raw.split("\n").map((item) => item.trim()).filter(Boolean));
    }} />;
}

export function Dates({ payload, update, allowCurrent = false }) {
    return (
        <div className="form-grid form-grid--3">
            <Input label="Inizio" type="date" value={payload.start_date || ""} onChange={(event) => update("start_date", event.target.value)} />
            <Input label="Fine" type="date" value={payload.end_date || ""} disabled={allowCurrent && payload.current} onChange={(event) => update("end_date", event.target.value)} />
            {allowCurrent && <label className="check-line check-line--field"><input type="checkbox" checked={Boolean(payload.current)} onChange={(event) => update("current", event.target.checked)} /> In corso</label>}
        </div>
    );
}
