import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const frontendRoot = resolve(fileURLToPath(new URL("../", import.meta.url)));
const bootstrapCss = await readFile(
  resolve(frontendRoot, "node_modules/bootstrap/dist/css/bootstrap.min.css"),
  "utf8",
);
const careerOsCss = await readFile(resolve(frontendRoot, "src/career-os.css"), "utf8");
const widths = [320, 390, 768, 1280];

const markup = `
  <div class="workspace-layout">
    <a class="skip-link" href="#main-content" inert aria-hidden="true">Skip to content</a>
    <div
      id="workspace-sidebar"
      class="workspace-sidebar is-open"
      role="dialog"
      aria-modal="true"
      aria-label="Main navigation"
    >
      <div class="workspace-brand">
        <div><strong>CareerOS</strong><span>private workspace</span></div>
        <button type="button" class="icon-button workspace-sidebar__close">Close</button>
      </div>
      <nav class="workspace-nav">
        <a class="workspace-nav__link is-active" href="#main-content">Today</a>
        <a class="workspace-nav__link" href="#jobs">Jobs</a>
      </nav>
    </div>
    <button
      type="button"
      class="workspace-scrim is-visible"
      aria-hidden="true"
      tabindex="-1"
    ></button>
    <div class="workspace-main" inert aria-hidden="true">
      <header class="workspace-header">
        <button type="button" class="icon-button workspace-menu">Menu</button>
        <div class="workspace-header__brand"><span>CareerOS Local</span></div>
        <div class="workspace-header__context">
          <span class="page-eyebrow">CareerOS Local</span>
          <h1>Your career workspace</h1>
          <p>Your facts, decisions and next steps. All on this device.</p>
        </div>
        <div class="privacy-chip">On this device</div>
      </header>
      <main id="main-content" class="workspace-content">
        <section class="surface-section"><h2>Next action</h2><p>Review an application.</p></section>
      </main>
    </div>
  </div>
`;

async function settle(page) {
  await page.evaluate(
    () => new Promise((resolveFrame) =>
      requestAnimationFrame(() => requestAnimationFrame(resolveFrame))),
  );
}

function milliseconds(duration) {
  const values = duration.split(",").map((value) => value.trim());
  return Math.max(...values.map((value) =>
    value.endsWith("ms") ? Number.parseFloat(value) : Number.parseFloat(value) * 1000));
}

const browser = await chromium.launch({ headless: true });

try {
  const page = await browser.newPage({ viewport: { width: widths[0], height: 900 } });
  await page.setContent(`
    <!doctype html>
    <html lang="en" data-bs-theme="dark">
      <head><style>${bootstrapCss}</style><style>${careerOsCss}</style></head>
      <body>${markup}</body>
    </html>
  `);

  assert.equal(
    await page.locator('.workspace-sidebar[role="dialog"][aria-modal="true"]').count(),
    1,
    "The open mobile navigation must expose one modal drawer",
  );
  assert.equal(
    await page.locator(".workspace-main[inert][aria-hidden='true']").count(),
    1,
    "The obscured workspace must be inert and hidden from assistive technology",
  );
  assert.equal(
    await page.locator(".workspace-scrim[aria-hidden='true'][tabindex='-1']").count(),
    1,
    "The visual scrim must not compete with the labelled close control",
  );

  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 });
    await settle(page);
    const report = await page.evaluate(() => {
      const box = (selector) => {
        const bounds = document.querySelector(selector).getBoundingClientRect();
        return {
          left: bounds.left,
          right: bounds.right,
          top: bounds.top,
          bottom: bounds.bottom,
          width: bounds.width,
          height: bounds.height,
        };
      };
      const scrimStyle = getComputedStyle(document.querySelector(".workspace-scrim"));
      return {
        viewportWidth: document.documentElement.clientWidth,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        sidebar: box(".workspace-sidebar"),
        main: box(".workspace-main"),
        header: box(".workspace-header"),
        menu: box(".workspace-menu"),
        brand: box(".workspace-header__brand"),
        context: box(".workspace-header__context"),
        heading: box(".workspace-header__context h1"),
        scrim: box(".workspace-scrim"),
        scrimDisplay: scrimStyle.display,
        scrimOpacity: scrimStyle.opacity,
      };
    });

    assert.equal(report.documentWidth, report.viewportWidth, `${width}px: no document overflow`);
    assert.equal(report.bodyWidth, report.viewportWidth, `${width}px: no body overflow`);
    assert(report.sidebar.width > 0, `${width}px: sidebar must have visible geometry`);
    assert(report.sidebar.left >= -1, `${width}px: sidebar must stay inside the left edge`);
    assert(
      report.sidebar.right <= report.viewportWidth + 1,
      `${width}px: sidebar must stay inside the right edge`,
    );
    assert(report.main.left >= 0, `${width}px: workspace must stay inside the viewport`);
    assert(
      report.main.right <= report.viewportWidth + 1,
      `${width}px: workspace must stay inside the right edge`,
    );
    assert(
      report.heading.width >= report.context.width - 1,
      `${width}px: heading must use the full intro column (${JSON.stringify(report)})`,
    );

    if (width < 992) {
      const minimumIntroWidth = report.main.width - 64;
      assert(
        report.context.width >= minimumIntroWidth,
        `${width}px: intro is only ${report.context.width}px; expected at least ${minimumIntroWidth}px`,
      );
      assert(
        report.context.top >= Math.max(report.menu.bottom, report.brand.bottom) - 1,
        `${width}px: intro must occupy a full row below menu and brand`,
      );
      assert.equal(report.scrimDisplay, "block", `${width}px: scrim must cover the mobile layout`);
      assert.equal(report.scrimOpacity, "1", `${width}px: open scrim must be visible`);
      assert.equal(report.scrim.left, 0, `${width}px: scrim must start at the viewport edge`);
      assert.equal(report.scrim.right, report.viewportWidth, `${width}px: scrim must span the viewport`);
    } else {
      assert(
        report.context.width >= report.main.width * 0.55,
        `${width}px: desktop intro must retain a professional reading width`,
      );
      assert.equal(report.sidebar.width, 272, "Desktop sidebar must retain its persistent width");
      assert.equal(report.scrimDisplay, "none", "Desktop layout must not retain the mobile scrim");
      assert.equal(report.main.left, 272, "Desktop workspace must remain offset by the sidebar");
    }
  }

  const reducedContext = await browser.newContext({
    reducedMotion: "reduce",
    viewport: { width: 375, height: 900 },
  });
  try {
    const reducedPage = await reducedContext.newPage();
    await reducedPage.setContent(`
      <!doctype html>
      <html lang="en"><head><style>${bootstrapCss}</style><style>${careerOsCss}</style></head>
      <body>${markup}</body></html>
    `);
    await settle(reducedPage);
    const transitions = await reducedPage.evaluate(() => ({
      sidebar: getComputedStyle(document.querySelector(".workspace-sidebar")).transitionDuration,
      scrim: getComputedStyle(document.querySelector(".workspace-scrim")).transitionDuration,
    }));
    assert(
      milliseconds(transitions.sidebar) <= 0.01,
      `Reduced-motion sidebar transition must be suppressed (${transitions.sidebar})`,
    );
    assert(
      milliseconds(transitions.scrim) <= 0.01,
      `Reduced-motion scrim transition must be suppressed (${transitions.scrim})`,
    );
  } finally {
    await reducedContext.close();
  }

  console.log(
    `Workspace shell geometry and reduced-motion validation passed at ${widths.length} viewport widths.`,
  );
} finally {
  await browser.close();
}
