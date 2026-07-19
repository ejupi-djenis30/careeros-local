import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { Sidebar } from "../components/Layout/Sidebar";
import { useAuth } from "../context/AuthContext";
import { PAGE_CONTEXT } from "./navigation";

export function WorkspaceShell({ children }) {
    const { user, logout } = useAuth();
    const { pathname } = useLocation();
    const [menuOpen, setMenuOpen] = useState(false);
    const menuButtonRef = useRef(null);
    const sidebarRef = useRef(null);
    const context = PAGE_CONTEXT[pathname] || PAGE_CONTEXT["/"];

    useEffect(() => {
        if (!menuOpen) return undefined;
        const sidebar = sidebarRef.current;
        const previouslyFocused = document.activeElement;
        const focusableSelector = "a[href], button:not([disabled]), [tabindex]:not([tabindex='-1'])";
        sidebar?.querySelector(focusableSelector)?.focus();

        const handleKeyDown = (event) => {
            if (event.key === "Escape") {
                event.preventDefault();
                setMenuOpen(false);
                return;
            }
            if (event.key !== "Tab" || !sidebar) return;
            const focusable = [...sidebar.querySelectorAll(focusableSelector)];
            if (focusable.length === 0) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        };
        document.addEventListener("keydown", handleKeyDown);
        return () => {
            document.removeEventListener("keydown", handleKeyDown);
            if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus();
        };
    }, [menuOpen]);

    return (
        <div className="workspace-layout">
            <a className="skip-link" href="#main-content">Vai al contenuto</a>
            <Sidebar
                username={user}
                onLogout={logout}
                isOpen={menuOpen}
                onClose={() => setMenuOpen(false)}
                containerRef={sidebarRef}
            />
            <button
                type="button"
                className={`workspace-scrim ${menuOpen ? "is-visible" : ""}`}
                onClick={() => setMenuOpen(false)}
                aria-label="Chiudi menu"
                aria-hidden={!menuOpen}
                tabIndex={menuOpen ? 0 : -1}
            />
            <div className="workspace-main">
                <header className="workspace-header">
                    <button
                        ref={menuButtonRef}
                        type="button"
                        className="icon-button workspace-menu"
                        onClick={() => setMenuOpen(true)}
                        aria-label="Apri menu"
                        aria-controls="workspace-sidebar"
                        aria-expanded={menuOpen}
                    >
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
