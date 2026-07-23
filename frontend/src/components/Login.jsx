import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { LanguageSwitcher } from "../i18n/LanguageSwitcher";
import { useI18n } from "../i18n/useI18n";
import { CAREEROS_MARK_URL } from "../app/brand";

export function Login() {
    const [mode, setMode] = useState("login");
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(false);
    const { login, register } = useAuth();
    const { t } = useI18n();

    const submit = async (event) => {
        event.preventDefault();
        setError(null);
        if (mode === "register" && (password.length < 8 || !/[A-Z]/.test(password) || !/\d/.test(password))) {
            setError({ messageKey: "login.passwordRule" });
            return;
        }
        setLoading(true);
        try {
            if (mode === "register") await register(username.trim(), password);
            else await login(username.trim(), password);
        } catch (authError) {
            setError({ message: authError.message, messageKey: authError.messageKey });
        } finally {
            setLoading(false);
        }
    };

    return (
        <main className="login-shell">
            <section className="login-story">
                <div className="workspace-brand workspace-brand--login">
                    <img className="workspace-brand__mark" src={CAREEROS_MARK_URL} alt="" width="40" height="40" />
                    <div><strong>CareerOS</strong><span>{t("login.privateWorkspace")}</span></div>
                </div>
                <div>
                    <span className="page-eyebrow">{t("login.eyebrow")}</span>
                    <h1>{t("login.heroTitle")}</h1>
                    <p>{t("login.heroCopy")}</p>
                </div>
                <ul>
                    <li><i className="bi bi-device-ssd" /><span><strong>{t("login.privateArchive")}</strong>{t("login.privateArchiveCopy")}</span></li>
                    <li><i className="bi bi-cpu" /><span><strong>{t("login.localAi")}</strong>{t("login.localAiCopy")}</span></li>
                    <li><i className="bi bi-patch-check" /><span><strong>{t("login.grounded")}</strong>{t("login.groundedCopy")}</span></li>
                </ul>
                <footer>{t("login.footer")}</footer>
            </section>
            <section className="login-panel" aria-labelledby="login-title">
                <LanguageSwitcher />
                <div className="login-panel__intro"><span className="login-lock"><i className="bi bi-lock" /></span><div><span className="section-kicker">{t("login.localSession")}</span><h2 id="login-title">{mode === "login" ? t("login.welcome") : t("login.createWorkspace")}</h2><p>{mode === "login" ? t("login.signInCopy") : t("login.registerCopy")}</p></div></div>
                {error && <div className="inline-alert inline-alert--danger" role="alert">{error.messageKey ? t(error.messageKey) : error.message}</div>}
                <form onSubmit={submit}>
                    <label className="field-stack"><span>{t("login.username")}</span><div className="input-with-icon"><i className="bi bi-person" /><input className="form-control" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus autoComplete="username" /></div></label>
                    <label className="field-stack"><span>{t("login.password")}</span><div className="input-with-icon"><i className="bi bi-key" /><input className="form-control" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete={mode === "register" ? "new-password" : "current-password"} /></div></label>
                    {mode === "register" && <p className="password-hint">{t("login.passwordRule")}</p>}
                    <button className="button button--primary button--wide" disabled={loading || !username.trim() || !password}>{loading ? t("login.checking") : mode === "login" ? t("login.signIn") : t("login.createAccount")}<i className="bi bi-arrow-right" /></button>
                </form>
                <button type="button" className="login-switch" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}>{mode === "login" ? t("login.firstTime") : t("login.hasAccount")}</button>
                <div className="login-privacy"><i className="bi bi-shield-lock" /><span>{t("login.privacy")}</span></div>
            </section>
        </main>
    );
}
