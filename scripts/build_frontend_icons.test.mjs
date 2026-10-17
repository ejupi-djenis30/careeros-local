import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { optimizeSvg, svgDataUrl } from "./build_frontend_icons.mjs";

test("generated icon subsets identify the locked upstream release", async () => {
    const lockfile = JSON.parse(await readFile(new URL("../frontend/package-lock.json", import.meta.url), "utf8"));
    const { version } = lockfile.packages["node_modules/bootstrap-icons"];
    for (const file of ["bootstrap-icons-subset.css", "shell-icons.css"]) {
        const stylesheet = await readFile(new URL(`../frontend/src/${file}`, import.meta.url), "utf8");
        assert.equal(
            stylesheet.split(/\r?\n/)[1],
            ` * Generated from Bootstrap Icons v${version} (https://icons.getbootstrap.com/)`,
        );
    }
});

test("the icon optimizer accepts the locked Bootstrap shape vocabulary", () => {
    assert.equal(
        optimizeSvg('<svg viewBox="0 0 16 16">\n  <g><path d="M1 2"/></g>\n</svg>', "safe"),
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><g><path d="M1 2"/></g></svg>',
    );
});

test("the icon optimizer rejects active or ambiguous SVG markup", () => {
    const unsafe = [
        '<svg><!-- <script>alert(1)</script> --><path d="M1 2"/></svg>',
        '<svg><script>alert(1)</script></svg>',
        '<svg><foreignObject><div>unsafe</div></foreignObject></svg>',
        '<svg><path onload="alert(1)" d="M1 2"/></svg>',
        '<svg><path style="fill:url(https://example.test/x)" d="M1 2"/></svg>',
        '<svg><use href="https://example.test/icon.svg#mark"/></svg>',
        '<svg><path d="M1 2"/>trailing text</svg>',
        '<svg><g><path d="M1 2"/></svg>',
    ];

    for (const [index, svg] of unsafe.entries()) {
        assert.throws(() => optimizeSvg(svg, `unsafe-${index}`), /unsupported|unsafe|malformed/);
    }
});

test("the CSS data URL encodes markup delimiters and quotes", () => {
    const value = svgDataUrl('<svg viewBox="0 0 1 1"><path d="M0 0"/></svg>');

    assert.match(value, /^url\("data:image\/svg\+xml,/);
    assert.doesNotMatch(value, /[<>]/);
    assert.equal((value.match(/"/g) ?? []).length, 2);
});
