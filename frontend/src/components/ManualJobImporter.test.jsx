import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithItalian as render } from "../test/renderWithI18n";
import { assertAccessible } from "../test/accessibility";
import { ManualJobImporter } from "./ManualJobImporter";

const importManual = vi.fn();

vi.mock("../services/jobs", () => ({
  JobService: { importManual: (...args) => importManual(...args) },
}));

describe("ManualJobImporter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    importManual.mockResolvedValue({ id: 42 });
  });

  it("stores a manually captured listing without any model action", async () => {
    const user = userEvent.setup();
    const onImported = vi.fn();
    const { container } = render(<ManualJobImporter onImported={onImported} />);

    await user.click(screen.getByRole("button", { name: "Importa annuncio" }));
    await user.type(screen.getByLabelText("Ruolo"), "Platform Engineer");
    await user.type(screen.getByLabelText("Azienda"), "Local Systems");
    await user.type(screen.getByLabelText("URL della fonte"), "https://example.test/jobs/42");
    await user.type(screen.getByLabelText("Località"), "Zurich");
    await user.click(screen.getByRole("button", { name: "Salva annuncio" }));

    await waitFor(() => expect(importManual).toHaveBeenCalledWith({
      title: "Platform Engineer",
      company: "Local Systems",
      external_url: "https://example.test/jobs/42",
      location: "Zurich",
      description: null,
    }));
    expect(onImported).toHaveBeenCalledTimes(1);
    await assertAccessible(container);
  });
});
