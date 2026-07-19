import { NavLink } from "react-router-dom";
import { LocalModelStatus } from "../../features/local-model/LocalModelStatus";
import { NAVIGATION } from "../../app/navigation";

export function Sidebar({ username, onLogout, isOpen, onClose, containerRef }) {
    return (
        <aside
            id="workspace-sidebar"
            ref={containerRef}
            className={`workspace-sidebar ${isOpen ? "is-open" : ""}`}
            aria-label="Navigazione principale"
        >
            <div className="workspace-brand">
                <div className="workspace-brand__mark" aria-hidden="true">C</div>
                <div>
                    <strong>CareerOS</strong>
                    <span>local workspace</span>
                </div>
                <button type="button" className="icon-button workspace-sidebar__close" onClick={onClose} aria-label="Chiudi menu">
                    <i className="bi bi-x-lg" aria-hidden="true" />
                </button>
            </div>

            <nav className="workspace-nav">
                {NAVIGATION.map((group) => (
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
                <LocalModelStatus compact />
                <div className="workspace-account">
                    <span className="workspace-account__avatar" aria-hidden="true">{username?.slice(0, 1)?.toUpperCase()}</span>
                    <div><strong>{username}</strong><span>Dati locali</span></div>
                    <button type="button" className="icon-button" onClick={onLogout} aria-label="Esci">
                        <i className="bi bi-box-arrow-right" aria-hidden="true" />
                    </button>
                </div>
            </div>
        </aside>
    );
}
