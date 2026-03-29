import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";

export function Login() {
    const [mode, setMode] = useState("login"); // login | register
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    const { login, register } = useAuth();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError("");
        setLoading(true);

        try {
            if (mode === "register") {
                if (password.length < 8 || !/[A-Z]/.test(password) || !/\d/.test(password)) {
                    setError("Password must be at least 8 characters, contain an uppercase letter and a number.");
                    setLoading(false);
                    return;
                }
                await register(username, password);
            } else {
                await login(username, password);
            }
            // `isLoggedIn` state will automatically flip to true from AuthContext, triggering App.jsx to render DashboardLayout
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-vh-100 d-flex align-items-center justify-content-center position-relative overflow-hidden">

            {/* Ambient Background Elements Removed */}

            <div className="glass-panel p-5 animate-slide-up position-relative" style={{ width: "100%", maxWidth: 420 }}>
                <div className="text-center mb-5">
                    <div className="d-inline-flex align-items-center justify-content-center rounded-circle mb-4"
                         style={{
                             width: 80, height: 80,
                             background: 'linear-gradient(135deg, rgba(79, 70, 229, 0.2), rgba(139, 92, 246, 0.2))',
                             border: '1px solid rgba(255,255,255,0.1)',
                             boxShadow: '0 0 30px rgba(79, 70, 229, 0.2)'
                         }}>
                        <i className="bi bi-search fs-1 text-white"></i>
                    </div>
                    <h2 className="fw-bold text-white mb-2 tracking-tight display-6">
                        JobHunter
                    </h2>
                    <p className="text-secondary opacity-75">
                        {mode === "login" ? "Welcome back, hunter" : "Join the hunt"}
                    </p>
                </div>

                {error && (
                    <div className="p-3 mb-4 rounded-3 bg-danger bg-opacity-10 text-danger border border-danger border-opacity-20 text-center small animate-fade-in">
                        <i className="bi bi-exclamation-circle-fill me-2"></i>
                        {error}
                    </div>
                )}

                <form onSubmit={handleSubmit}>
                    <div className="mb-4">
                        <label className="text-secondary text-uppercase x-small fw-bold mb-2 ps-1" style={{fontSize: '0.75rem'}}>Username</label>
                        <div className="position-relative">
                            <span className="position-absolute top-50 start-0 translate-middle-y ps-3 text-secondary">
                                <i className="bi bi-person"></i>
                            </span>
                            <input
                                type="text"
                                id="username"
                                name="username"
                                className="form-control"
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                required
                                autoFocus
                                autoComplete={mode === "register" ? "username" : "username"}
                                placeholder="Enter your username"
                                style={{ paddingLeft: '2.8rem', height: '3.2rem' }}
                            />
                        </div>
                    </div>

                    <div className="mb-5">
                        <label className="text-secondary text-uppercase x-small fw-bold mb-2 ps-1" style={{fontSize: '0.75rem'}}>Password</label>
                        <div className="position-relative">
                            <span className="position-absolute top-50 start-0 translate-middle-y ps-3 text-secondary">
                                <i className="bi bi-lock"></i>
                            </span>
                            <input
                                type="password"
                                id="password"
                                name="password"
                                className="form-control"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                required
                                autoComplete={mode === "register" ? "new-password" : "current-password"}
                                placeholder="••••••••"
                                style={{ paddingLeft: '2.8rem', height: '3.2rem' }}
                            />
                        </div>
                    </div>

                    <button
                        type="submit"
                        className="btn btn-primary w-100 py-3 fw-bold shadow-lg"
                        disabled={loading || !username || !password}
                        style={{ height: '3.5rem', fontSize: '1.05rem' }}
                    >
                        {loading ? (
                            <span className="spinner-border spinner-border-sm me-2" />
                        ) : null}
                        {mode === "login" ? (
                            <><i className="bi bi-box-arrow-in-right me-2"></i>Sign In</>
                        ) : (
                            <><i className="bi bi-rocket-takeoff me-2"></i>Create Account</>
                        )}
                    </button>
                </form>

                <div className="text-center pt-4 mt-2 border-top border-white-10">
                    <button
                        className="btn btn-link text-secondary text-decoration-none small opacity-75 hover-opacity-100"
                        onClick={() => {
                            setMode(mode === "login" ? "register" : "login");
                            setError("");
                        }}
                    >
                        {mode === "login"
                            ? "New here? Create an account"
                            : "Already have an account? Sign In"}
                    </button>
                </div>
            </div>
        </div>
    );
}
