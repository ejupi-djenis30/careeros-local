import { useState } from "react";
import { useAuth } from "../context/AuthContext";

export function Login() {
    const [mode, setMode] = useState("login");
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const { login, register } = useAuth();

    const submit = async (event) => {
        event.preventDefault();
        setError("");
        if (mode === "register" && (password.length < 8 || !/[A-Z]/.test(password) || !/\d/.test(password))) {
            setError("Usa almeno 8 caratteri, una maiuscola e un numero.");
            return;
        }
        setLoading(true);
        try {
            if (mode === "register") await register(username.trim(), password);
            else await login(username.trim(), password);
        } catch (authError) {
            setError(authError.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <main className="login-shell">
            <section className="login-story">
                <div className="workspace-brand workspace-brand--login"><div className="workspace-brand__mark">C</div><div><strong>CareerOS</strong><span>local workspace</span></div></div>
                <div><span className="page-eyebrow">Il tuo agente carriera personale</span><h1>La memoria professionale che resta tua.</h1><p>Profilo, CV, opportunità, candidature e coaching in un unico workspace locale.</p></div>
                <ul><li><i className="bi bi-device-ssd" /><span><strong>Local first</strong>Dati e documenti sul tuo dispositivo</span></li><li><i className="bi bi-cpu" /><span><strong>Modelli locali</strong>Inferenza tramite Ollama, senza fallback cloud</span></li><li><i className="bi bi-patch-check" /><span><strong>Fatti verificabili</strong>Provenienza, revisioni e artefatti immutabili</span></li></ul>
                <footer>CareerOS funziona anche senza modello: il tuo archivio resta sempre accessibile.</footer>
            </section>
            <section className="login-panel" aria-labelledby="login-title">
                <div className="login-panel__intro"><span className="login-lock"><i className="bi bi-lock" /></span><div><span className="section-kicker">Sessione locale</span><h2 id="login-title">{mode === "login" ? "Bentornato" : "Crea il tuo workspace"}</h2><p>{mode === "login" ? "Accedi ai dati salvati su questo dispositivo." : "L’account protegge il tuo archivio locale."}</p></div></div>
                {error && <div className="inline-alert inline-alert--danger" role="alert">{error}</div>}
                <form onSubmit={submit}>
                    <label className="field-stack"><span>Nome utente</span><div className="input-with-icon"><i className="bi bi-person" /><input className="form-control" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus autoComplete="username" /></div></label>
                    <label className="field-stack"><span>Password</span><div className="input-with-icon"><i className="bi bi-key" /><input className="form-control" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete={mode === "register" ? "new-password" : "current-password"} /></div></label>
                    {mode === "register" && <p className="password-hint">Almeno 8 caratteri, una maiuscola e un numero.</p>}
                    <button className="button button--primary button--wide" disabled={loading || !username.trim() || !password}>{loading ? "Verifica…" : mode === "login" ? "Accedi al workspace" : "Crea account locale"}<i className="bi bi-arrow-right" /></button>
                </form>
                <button type="button" className="login-switch" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>{mode === "login" ? "Primo accesso? Crea un account locale" : "Hai già un account? Accedi"}</button>
                <div className="login-privacy"><i className="bi bi-shield-lock" /><span>Le credenziali vengono gestite dal backend locale. Nessun servizio di identità esterno.</span></div>
            </section>
        </main>
    );
}
