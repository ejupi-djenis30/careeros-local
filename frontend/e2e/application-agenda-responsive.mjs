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
const agendaTimeSource = await readFile(
  resolve(frontendRoot, "src/features/applications/agendaTime.js"),
  "utf8",
);
const agendaTimeModuleUrl = `data:text/javascript;base64,${Buffer.from(agendaTimeSource).toString("base64")}`;
const widths = [320, 375, 768, 1280];
const contrastSelectors = [
  "#application-agenda-description",
  ".application-agenda__main strong",
  ".application-agenda__main small",
  ".application-agenda__item time",
  ".application-agenda__omissions",
  ".agenda-state--overdue",
  ".agenda-state--today",
  ".agenda-state--upcoming",
  ".agenda-state--needs_action",
];

const markup = `
  <main class="agenda-harness">
    <section class="surface-section application-agenda" aria-labelledby="application-agenda-title" aria-describedby="application-agenda-description">
      <div class="section-heading">
        <div>
          <span class="section-kicker">TODAY</span>
          <h2 id="application-agenda-title">Next actions</h2>
          <p id="application-agenda-description">A private, deterministic queue built from the applications stored on this device.</p>
        </div>
        <strong class="application-agenda__count">4</strong>
      </div>
      <div class="application-agenda__list">
        <button type="button" class="application-agenda__item">
          <span class="agenda-state agenda-state--overdue">Overdue</span>
          <span class="application-agenda__main">
            <strong>Send a thoughtful follow-up with the hiring manager</strong>
            <small>Senior Platform Reliability Engineer · Private Research Systems</small>
          </span>
          <time datetime="2026-07-23T10:15:00Z">Thu, 23 Jul, 12:15</time>
          <i aria-hidden="true">→</i>
        </button>
        <button type="button" class="application-agenda__item">
          <span class="agenda-state agenda-state--today">Today</span>
          <span class="application-agenda__main">
            <strong>Prepare the system-design interview notes</strong>
            <small>Machine Learning Engineer · Confidential employer</small>
          </span>
          <time datetime="2026-07-23T16:30:00Z">Thu, 23 Jul, 18:30</time>
          <i aria-hidden="true">→</i>
        </button>
        <button type="button" class="application-agenda__item">
          <span class="agenda-state agenda-state--upcoming">Upcoming</span>
          <span class="application-agenda__main">
            <strong>Review the role before applying</strong>
            <small>Staff Software Engineer · Local Systems</small>
          </span>
          <time datetime="2026-07-25T08:00:00Z">Sat, 25 Jul, 10:00</time>
          <i aria-hidden="true">→</i>
        </button>
        <button type="button" class="application-agenda__item">
          <span class="agenda-state agenda-state--needs_action">Action missing</span>
          <span class="application-agenda__main">
            <strong>Set a next action</strong>
            <small>Product Engineer · Privacy-first company</small>
          </span>
          <span class="application-agenda__no-date">No deadline</span>
          <i aria-hidden="true">→</i>
        </button>
      </div>
      <p class="application-agenda__omissions">Beyond the seven-day horizon: 12. Not shown because of the compact limit: 8.</p>
    </section>
  </main>
`;

const browser = await chromium.launch({ headless: true });

try {
  const page = await browser.newPage({ viewport: { width: widths[0], height: 900 } });
  await page.setContent(`
    <!doctype html>
    <html lang="en">
      <head>
        <style>${bootstrapCss}</style>
        <style>${careerOsCss}</style>
        <style>.agenda-harness { width: 100%; max-width: 960px; margin: 0 auto; padding: 12px; }</style>
      </head>
      <body>${markup}</body>
    </html>
  `);

  assert.equal(
    await page.locator("section[aria-labelledby][aria-describedby]").count(),
    1,
    "Agenda must expose one labelled and described region",
  );

  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 });
    await page.evaluate(
      () =>
        new Promise((resolveFrame) =>
          requestAnimationFrame(() => requestAnimationFrame(resolveFrame)),
        ),
    );

    const report = await page.evaluate((selectors) => {
      const parseColor = (value) => {
        const channels = value.match(/[\d.]+/g)?.map(Number) ?? [];
        return {
          r: channels[0] ?? 0,
          g: channels[1] ?? 0,
          b: channels[2] ?? 0,
          a: channels.length > 3 ? channels[3] : 1,
        };
      };
      const composite = (foreground, background) => {
        const alpha = foreground.a + background.a * (1 - foreground.a);
        if (alpha === 0) return { r: 0, g: 0, b: 0, a: 0 };
        return {
          r: (foreground.r * foreground.a + background.r * background.a * (1 - foreground.a)) / alpha,
          g: (foreground.g * foreground.a + background.g * background.a * (1 - foreground.a)) / alpha,
          b: (foreground.b * foreground.a + background.b * background.a * (1 - foreground.a)) / alpha,
          a: alpha,
        };
      };
      const effectiveBackground = (element) => {
        const layers = [];
        for (let current = element; current; current = current.parentElement) {
          layers.push(parseColor(getComputedStyle(current).backgroundColor));
        }
        let color = { r: 255, g: 255, b: 255, a: 1 };
        for (const layer of layers.reverse()) color = composite(layer, color);
        return color;
      };
      const luminance = ({ r, g, b }) => {
        const linear = [r, g, b].map((channel) => {
          const value = channel / 255;
          return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
        });
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
      };
      const contrast = (foreground, background) => {
        const light = Math.max(luminance(foreground), luminance(background));
        const dark = Math.min(luminance(foreground), luminance(background));
        return (light + 0.05) / (dark + 0.05);
      };
      const viewportWidth = document.documentElement.clientWidth;
      const measured = Array.from(
        document.querySelectorAll(".application-agenda, .application-agenda__item, .application-agenda__item > *"),
      ).map((element) => {
        const bounds = element.getBoundingClientRect();
        return {
          label: `${element.tagName.toLowerCase()}.${element.className}`,
          left: bounds.left,
          right: bounds.right,
          top: bounds.top,
          bottom: bounds.bottom,
          width: bounds.width,
          height: bounds.height,
        };
      });
      const overlaps = [];
      for (const row of document.querySelectorAll(".application-agenda__item")) {
        const children = Array.from(row.children);
        for (let first = 0; first < children.length; first += 1) {
          const a = children[first].getBoundingClientRect();
          for (let second = first + 1; second < children.length; second += 1) {
            const b = children[second].getBoundingClientRect();
            const overlapWidth = Math.min(a.right, b.right) - Math.max(a.left, b.left);
            const overlapHeight = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
            if (overlapWidth > 0.5 && overlapHeight > 0.5) {
              overlaps.push(`${children[first].className} / ${children[second].className}`);
            }
          }
        }
      }
      const contrasts = selectors.map((selector) => {
        const element = document.querySelector(selector);
        if (!element) return { selector, missing: true, ratio: 0 };
        return {
          selector,
          missing: false,
          ratio: contrast(
            parseColor(getComputedStyle(element).color),
            effectiveBackground(element),
          ),
        };
      });
      return {
        viewportWidth,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        measured,
        overlaps,
        contrasts,
      };
    }, contrastSelectors);

    assert.equal(report.documentWidth, report.viewportWidth, `${width}px: document must not scroll horizontally`);
    assert.equal(report.bodyWidth, report.viewportWidth, `${width}px: body must not scroll horizontally`);
    for (const box of report.measured) {
      assert(box.width > 0 && box.height > 0, `${width}px: ${box.label} must have visible geometry`);
      assert(box.left >= -1, `${width}px: ${box.label} crosses the left viewport edge`);
      assert(box.right <= report.viewportWidth + 1, `${width}px: ${box.label} crosses the right viewport edge`);
    }
    assert.deepEqual(report.overlaps, [], `${width}px: agenda content must not overlap`);
    for (const item of report.contrasts) {
      assert.equal(item.missing, false, `${width}px: missing contrast target ${item.selector}`);
      assert(
        item.ratio >= 4.5,
        `${width}px: ${item.selector} needs 4.5:1 contrast (received ${item.ratio.toFixed(2)}:1)`,
      );
    }
  }

  const zurich = await browser.newContext({ timezoneId: "Europe/Zurich" });
  try {
    const dstPage = await zurich.newPage();
    const boundaries = await dstPage.evaluate(async (moduleUrl) => {
      const { nextLocalDayEnd } = await import(moduleUrl);
      return [
        nextLocalDayEnd(new Date("2026-03-29T00:30:00+01:00")).toISOString(),
        nextLocalDayEnd(new Date("2026-10-25T00:30:00+02:00")).toISOString(),
      ];
    }, agendaTimeModuleUrl);
    assert.deepEqual(
      boundaries,
      ["2026-03-29T22:00:00.000Z", "2026-10-25T23:00:00.000Z"],
      "Browser-local midnight must follow Zurich daylight-saving transitions",
    );
  } finally {
    await zurich.close();
  }

  console.log(`Application agenda responsive, contrast and DST validation passed at ${widths.length} viewport widths.`);
} finally {
  await browser.close();
}
