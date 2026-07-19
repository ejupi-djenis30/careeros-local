import { NavLink } from "react-router-dom";
import { LocalModelStatus } from "../../features/local-model/LocalModelStatus";
import { LanguageSwitcher } from "../../i18n/LanguageSwitcher";
import { useI18n } from "../../i18n/useI18n";
import { getNavigation } from "../../app/navigation";

export function Sidebar({ username, onLogout, isOpen, onClose, containerRef }) {
    const { t } = useI18n();
    const navigation = getNavigation(t);
    return (
        <aside
            id="workspace-sidebar"
            ref={containerRef}
            className={`workspace-sidebar ${isOpen ? "is-open" : ""}`}
            aria-label={t("sidebar.navigation")}
        >
            <div className="workspace-brand">
                <img
                    className="workspace-brand__mark"
                    src="/careeros.svg"
                    alt=""
                    width="40"
                    height="40"
                    aria-hidden="true"
                />
                <div>
                    <strong>CareerOS</strong>
                    <span>{t("sidebar.privateWorkspace")}</span>
                </div>
                <button type="button" className="icon-button workspace-sidebar__close" onClick={onClose} aria-label={t("shell.closeMenu")}>
                    <i className="bi bi-x-lg" aria-hidden="true" />
                </button>
            </div>

            <nav className="workspace-nav">
                {navigation.map((group) => (
                    <section key={group.label} className="workspace-nav__group" aria-labelledby={`nav-${group.label.replace(/\s/g, "-")}`}>
                        <h2 id={`nav-${group.label.replace(/\s/g, "-")}`}>{group.label}</h2>
                        {group.items.map((item) => (
                            <NavLink
                                key={item.to}
                                to={item.to}
                                end={item.to === "/"}
                                onClick={onClose}
                                className={({ isActive }) => `workspace-nav__link ${isActive ? "is-active" : ""}`}
                            >
                                <i className={`bi ${item.icon}`} aria-hidden="true" />
                                <span>{item.label}</span>
                            </NavLink>
                        ))}
                    </section>
                ))}
            </nav>

            <div className="workspace-sidebar__footer">
                <LanguageSwitcher />
                <LocalModelStatus compact />
                <div className="workspace-account">
                    <span className="workspace-account__avatar" aria-hidden="true">{username?.slice(0, 1)?.toUpperCase()}</span>
                    <div><strong>{username}</strong><span>{t("sidebar.localData")}</span></div>
                    <button type="button" className="icon-button" onClick={onLogout} aria-label={t("sidebar.signOut")}>
                        <i className="bi bi-box-arrow-right" aria-hidden="true" />
                    </button>
                </div>
            </div>
        </aside>
    );
}
