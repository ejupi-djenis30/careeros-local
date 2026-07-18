import { useState } from "react";
import { useLocation } from "react-router-dom";
import { Sidebar } from "../components/Layout/Sidebar";
import { useAuth } from "../context/AuthContext";
import { PAGE_CONTEXT } from "./navigation";

export function WorkspaceShell({ children }) {
    const { user, logout } = useAuth();
    const { pathname } = useLocation();
    const [menuOpen, setMenuOpen] = useState(false);
    const context = PAGE_CONTEXT[pathname] || PAGE_CONTEXT["/"];

    return (
        <div className="workspace-layout">
            <a className="skip-link" href="#main-content">Vai al contenuto</a>
            <Sidebar username={user} onLogout={logout} isOpen={menuOpen} onClose={() => setMenuOpen(false)} />
            <button
                type="button"
                className={`workspace-scrim ${menuOpen ? "is-visible" : ""}`}
                onClick={() => setMenuOpen(false)}
                aria-label="Chiudi menu"
                tabIndex={menuOpen ? 0 : -1}
            />
            <div className="workspace-main">
                <header className="workspace-header">
                    <button type="button" className="icon-button workspace-menu" onClick={() => setMenuOpen(true)} aria-label="Apri menu">
                        <i className="bi bi-list" aria-hidden="true" />
                    </button>
                    <div>
                        <span className="page-eyebrow">{context.eyebrow}</span>
                        <h1>{context.title}</h1>
                        <p>{context.description}</p>
                    </div>
                    <div className="privacy-chip" title="Il database e gli artefatti restano sul dispositivo">
                        <i className="bi bi-shield-lock" aria-hidden="true" />
                        <span>Local first</span>
                    </div>
                </header>
                <main id="main-content" className="workspace-content" tabIndex="-1">{children}</main>
            </div>
        </div>
    );
}

