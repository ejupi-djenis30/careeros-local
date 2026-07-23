import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useLocationInput } from "./useLocationInput";
import { renderWithItalian as render } from "../test/renderWithI18n";

const showToast = vi.fn();
vi.mock("../context/ToastContext", () => ({ useToast: () => ({ showToast }) }));

function Consumer({ location = "", onChange = vi.fn() }) {
    const input = useLocationInput(location, onChange);
    return <><input aria-label="location" value={input.query} onChange={(event) => input.setQuery(event.target.value)} /><button onClick={input.handleCurrentLocation}>position</button><span>{String(input.isLoading)}</span></>;
}

describe("useLocationInput", () => {
    beforeEach(() => vi.clearAllMocks());
    afterEach(() => vi.restoreAllMocks());

    it("keeps a location name entirely local and clears stale coordinates", async () => {
        const onChange = vi.fn();
        const fetchSpy = vi.spyOn(globalThis, "fetch");
        render(<Consumer location="Zurich" onChange={onChange} />);
        await userEvent.type(screen.getByLabelText("location"), " West");
        expect(onChange).toHaveBeenLastCalledWith({ name: "Zurich West", lat: null, lon: null });
        expect(fetchSpy).not.toHaveBeenCalled();
    });

    it("syncs an externally changed location", () => {
        const { rerender } = render(<Consumer location="Bern" />);
        rerender(<Consumer location="Basel" />);
        expect(screen.getByLabelText("location")).toHaveValue("Basel");
    });

    it("uses browser coordinates without reverse geocoding", async () => {
        const onChange = vi.fn();
        const fetchSpy = vi.spyOn(globalThis, "fetch");
        Object.defineProperty(navigator, "geolocation", { configurable: true, value: { getCurrentPosition: vi.fn((success) => success({ coords: { latitude: 47.3769, longitude: 8.5417 } })) } });
        render(<Consumer onChange={onChange} />);
        await act(async () => screen.getByRole("button").click());
        expect(onChange).toHaveBeenLastCalledWith({ name: "47.37690, 8.54170", lat: 47.3769, lon: 8.5417 });
        expect(fetchSpy).not.toHaveBeenCalled();
    });

    it("reports unavailable geolocation", async () => {
        Object.defineProperty(navigator, "geolocation", { configurable: true, value: undefined });
        render(<Consumer />);
        await act(async () => screen.getByRole("button").click());
        expect(showToast).toHaveBeenCalledWith({ messageKey: "location.unsupported" });
    });
});
