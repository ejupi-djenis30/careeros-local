import { Component } from "react";

export class WorkspaceErrorBoundary extends Component {
    state = { failed: false };

    static getDerivedStateFromError() {
        return { failed: true };
    }

    render() {
        if (this.state.failed) {
            return (
                <div className="state-panel state-panel--danger" role="alert">
                    <i className="bi bi-exclamation-triangle" aria-hidden="true" />
                    <h2>{this.props.title}</h2>
                    <p>{this.props.description}</p>
                    <button type="button" className="button button--primary" onClick={() => window.location.reload()}>{this.props.reloadLabel}</button>
                </div>
            );
        }
        return this.props.children;
    }
}
