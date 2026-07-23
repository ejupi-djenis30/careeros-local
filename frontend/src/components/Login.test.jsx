import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n/I18nContext";
import { Login } from "./Login";

const auth = vi.hoisted(() => ({ login: vi.fn(), register: vi.fn() }));

vi.mock("../context/AuthContext", () => ({
    useAuth: () => auth,
}));

function renderLogin() {
    return render(<I18nProvider><Login /></I18nProvider>);
}

async function openRegistration(user) {
    await user.click(screen.getByRole("button", { name: "First time here? Create a local account" }));
    await user.type(screen.getByLabelText("Username"), "demo-user");
}

describe("Login localization", () => {
    beforeEach(() => {
        window.localStorage.clear();
        auth.login.mockReset();
        auth.register.mockReset();
    });

    it("retranslates a local validation error when the language changes", async () => {
        const user = userEvent.setup();
        renderLogin();
        await openRegistration(user);
        await user.type(screen.getByLabelText("Password"), "short");
        await user.click(screen.getByRole("button", { name: "Create local account" }));

        expect(screen.getByRole("alert")).toHaveTextContent("Use at least 8 characters, one uppercase letter and one number.");
        await user.click(screen.getByRole("button", { name: "Italian" }));
        expect(screen.getByRole("alert")).toHaveTextContent("Usa almeno 8 caratteri, una maiuscola e un numero.");
        expect(auth.register).not.toHaveBeenCalled();
    });

    it("retranslates an authentication fallback without rewriting server errors", async () => {
        const fallback = new Error("Registration failed. Please try again.");
        fallback.messageKey = "auth.registrationFailed";
        auth.register.mockRejectedValueOnce(fallback);
        const user = userEvent.setup();
        renderLogin();
        await openRegistration(user);
        await user.type(screen.getByLabelText("Password"), "Password1");
        await user.click(screen.getByRole("button", { name: "Create local account" }));

        expect(await screen.findByRole("alert")).toHaveTextContent("Registration failed. Please try again.");
        await user.click(screen.getByRole("button", { name: "Italian" }));
        expect(screen.getByRole("alert")).toHaveTextContent("Registrazione non riuscita. Riprova.");
    });
});
