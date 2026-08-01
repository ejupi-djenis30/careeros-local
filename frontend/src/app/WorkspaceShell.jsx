import { useLayoutEffect, useRef, useState } from "react";
import { useLocation } from "react-router";
import { Sidebar } from "../components/Layout/Sidebar";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n/useI18n";
import { CAREEROS_MARK_URL } from "./brand";
import { getPageContext } from "./navigation";

const DESKTOP_BREAKPOINT = 992;

export function WorkspaceShell({ children }) {
    const { user, logout } = useAuth();
    const { pathname } = useLocation();
    const [menuOpen, setMenuOpen] = useState(false);
    const menuButtonRef = useRef(null);
    const restoreFocusFrameRef = useRef(null);
    const sidebarRef = useRef(null);
    const { t } = useI18n();
    const context = getPageContext(pathname, t);

    useLayoutEffect(() => {
        if (!menuOpen) return undefined;
        if (restoreFocusFrameRef.current !== null) {
            window.cancelAnimationFrame(restoreFocusFrameRef.current);
            restoreFocusFrameRef.current = null;
        }
        const sidebar = sidebarRef.current;
        const returnFocus = menuButtonRef.current;
        const previousOverflow = document.body.style.overflow;
        const focusableSelector = "a[href], button:not([disabled]), [tabindex]:not([tabindex='-1'])";
        document.body.style.overflow = "hidden";
        const focusFrame = window.requestAnimationFrame(() => {
            const initialFocus = sidebar?.querySelector(focusableSelector);
            if (initialFocus instanceof HTMLElement) {
                initialFocus.focus({ preventScroll: true });
            }
        });

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
        const handleResize = () => {
            if (window.innerWidth >= DESKTOP_BREAKPOINT) setMenuOpen(false);
        };
        document.addEventListener("keydown", handleKeyDown);
        window.addEventListener("resize", handleResize);
        return () => {
            window.cancelAnimationFrame(focusFrame);
            document.removeEventListener("keydown", handleKeyDown);
            window.removeEventListener("resize", handleResize);
            document.body.style.overflow = previousOverflow;
            restoreFocusFrameRef.current = window.requestAnimationFrame(() => {
                restoreFocusFrameRef.current = null;
                if (
                    returnFocus instanceof HTMLElement
                    && returnFocus.isConnected
                ) returnFocus.focus({ preventScroll: true });
            });
        };
    }, [menuOpen]);

    return (
        <div className="workspace-layout">
            <a
                className="skip-link"
                href="#main-content"
                inert={menuOpen}
                aria-hidden={menuOpen || undefined}
            >
                {t("shell.skip")}
            </a>
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
                aria-hidden="true"
                tabIndex="-1"
            />
            <div
                className="workspace-main"
                inert={menuOpen}
                aria-hidden={menuOpen || undefined}
            >
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
