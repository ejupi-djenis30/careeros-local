import { act, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderWithI18n } from "../../test/renderWithI18n";
import { createTranslator } from "../../i18n/runtime";
import { ProviderImporter } from "./ProviderImporter";

const t = createTranslator("en");

describe("ProviderImporter boundaries", () => {
    it("rejects oversized documents before reading or submitting them", async () => {
        const onImport = vi.fn();
        const file = new File([new Uint8Array(256 * 1024 + 1)], "large.json", { type: "application/json" });
        const read = vi.fn();
        Object.defineProperty(file, "text", { value: read });
        renderWithI18n(<ProviderImporter packs={[]} onImportDocument={onImport} busy={false} t={t} />);
        await act(async () => { fireEvent.change(screen.getByLabelText(/Provider or provider-pack JSON file/), { target: { files: [file] } }); });
        expect(read).not.toHaveBeenCalled();
        expect(onImport).toHaveBeenCalledWith(null, false, expect.objectContaining({ message: "The provider document is larger than 256 KiB." }));
    });

    it.each(["{", "[]", "null", "42"])("rejects invalid document %s before an import request", async (content) => {
        const onImport = vi.fn();
        const file = new File([content], "provider.json", { type: "application/json" });
        Object.defineProperty(file, "text", { value: async () => content });
        renderWithI18n(<ProviderImporter packs={[]} onImportDocument={onImport} busy={false} t={t} />);
        await act(async () => { fireEvent.change(screen.getByLabelText(/Provider or provider-pack JSON file/), { target: { files: [file] } }); });
        expect(onImport).toHaveBeenCalledWith(null, false, expect.objectContaining({ message: "Choose a valid provider or provider-pack JSON document." }));
    });

    it("does not submit a file that finishes reading after the importer unmounts", async () => {
        let finish;
        const reading = new Promise((resolve) => { finish = resolve; });
        const onImport = vi.fn();
        const file = new File(["{}"], "provider.json", { type: "application/json" });
        Object.defineProperty(file, "text", { value: () => reading });
        const view = renderWithI18n(<ProviderImporter packs={[]} onImportDocument={onImport} busy={false} t={t} />);
        fireEvent.change(screen.getByLabelText(/Provider or provider-pack JSON file/), { target: { files: [file] } });
        view.unmount();
        await act(async () => { finish("{}"); await reading; });
        expect(onImport).not.toHaveBeenCalled();
    });
});
