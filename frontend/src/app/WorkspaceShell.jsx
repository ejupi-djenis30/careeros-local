import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { Sidebar } from "../components/Layout/Sidebar";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n/useI18n";
import { CAREEROS_MARK_URL } from "./brand";
import { getPageContext } from "./navigation";

export function WorkspaceShell({ children }) {
    const { user, logout } = useAuth();
    const { pathname } = useLocation();
    const [menuOpen, setMenuOpen] = useState(false);
    const menuButtonRef = useRef(null);
    const sidebarRef = useRef(null);
    const { t } = useI18n();
    const context = getPageContext(pathname, t);

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
            <a className="skip-link" href="#main-content">{t("shell.skip")}</a>
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
                aria-label={t("shell.closeMenu")}
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
                        aria-label={t("shell.openMenu")}
                        aria-controls="workspace-sidebar"
                        aria-expanded={menuOpen}
                    >
                        <i className="bi bi-list" aria-hidden="true" />
                    </button>
                    <div className="workspace-header__brand">
                        <img src={CAREEROS_MARK_URL} alt="CareerOS Local" width="36" height="36" />
                        <span aria-hidden="true">{t("page.home.eyebrow")}</span>
                    </div>
                    <div className="workspace-header__context">
                        <span className="page-eyebrow">{context.eyebrow}</span>
                        <h1>{context.title}</h1>
                        <p>{context.description}</p>
                    </div>
                    <div className="privacy-chip" title={t("shell.privateTitle")}>
                        <i className="bi bi-shield-lock" aria-hidden="true" />
                        <span>{t("shell.private")}</span>
                    </div>
                </header>
                <main id="main-content" className="workspace-content" tabIndex="-1">{children}</main>
            </div>
        </div>
    );
}
