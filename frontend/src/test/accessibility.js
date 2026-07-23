import axe from "axe-core";

function formatViolation(violation) {
    const targets = violation.nodes
        .flatMap((node) => node.target)
        .join(", ");
    return `${violation.id}: ${violation.help} (${targets})`;
}

export async function assertAccessible(container) {
    const result = await axe.run(container, {
        rules: {
            // JSDOM does not perform layout or compute real colors.
            "color-contrast": { enabled: false },
        },
    });
    if (result.violations.length > 0) {
        throw new Error(result.violations.map(formatViolation).join("\n"));
    }
}
