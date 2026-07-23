import assert from "node:assert/strict";
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, normalize, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const siteRoot = resolve(fileURLToPath(new URL("../../docs/", import.meta.url)));
const mountPath = "/careeros-local";
const widths = [320, 375, 720, 721, 1020, 1021, 1180, 1240, 1256, 1270, 1271, 1280, 1425, 1600];
const measuredSelectors = [
  ".nav.container",
  ".brand",
  ".nav-cta",
  ".container.hero-grid",
  ".hero-copy",
  "h1",
  ".hero-visual",
  ".product-window",
  ".principle-strip",
  ".feature-card",
  ".feature-copy",
  ".readiness-console",
  ".container.demo-grid",
  ".demo-copy",
  ".video-shell",
  ".container.privacy-grid",
  ".privacy-copy",
  ".trust-card",
  ".engineering-heading",
  ".stack-grid",
  ".quality-bar",
  ".cta-card",
  ".footer-grid",
];

const contentTypes = new Map([
  [".avif", "image/avif"],
  [".css", "text/css; charset=utf-8"],
  [".gif", "image/gif"],
  [".html", "text/html; charset=utf-8"],
  [".jpg", "image/jpeg"],
  [".json", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml"],
  [".txt", "text/plain; charset=utf-8"],
  [".webm", "video/webm"],
  [".webp", "image/webp"],
]);

function resolveRequestPath(requestUrl) {
  const pathname = new URL(requestUrl ?? "/", "http://127.0.0.1").pathname;
  const decoded = decodeURIComponent(pathname);
  if (decoded !== mountPath && !decoded.startsWith(`${mountPath}/`)) return null;
  const mountedPath = decoded.slice(mountPath.length) || "/";
  const requested = mountedPath.endsWith("/") ? `${mountedPath}index.html` : mountedPath;
  const candidate = resolve(siteRoot, `.${normalize(requested)}`);
  const pathWithinSite = relative(siteRoot, candidate);

  if (pathWithinSite === "" || pathWithinSite.startsWith(`..${sep}`) || pathWithinSite === "..") {
    return null;
  }
  return candidate;
}

function startStaticServer() {
  const server = createServer(async (request, response) => {
    const path = resolveRequestPath(request.url);
    if (!path) {
      response.writeHead(403).end("Forbidden");
      return;
    }

    try {
      const metadata = await stat(path);
      if (!metadata.isFile()) throw new Error("Not a file");
      response.writeHead(200, {
        "Cache-Control": "no-store",
        "Content-Length": metadata.size,
        "Content-Type": contentTypes.get(extname(path).toLowerCase()) ?? "application/octet-stream",
      });
      createReadStream(path).pipe(response);
    } catch {
      response.writeHead(404).end("Not found");
    }
  });

  return new Promise((resolveServer, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => resolveServer(server));
  });
}

function closeServer(server) {
  return new Promise((resolveClose, reject) => {
    server.close((error) => (error ? reject(error) : resolveClose()));
  });
}

const server = await startStaticServer();
const address = server.address();
assert(address && typeof address !== "string", "Static test server did not expose a TCP port");
const baseUrl = `http://127.0.0.1:${address.port}${mountPath}/`;
const browser = await chromium.launch({ headless: true });

try {
  const page = await browser.newPage({ viewport: { width: widths[0], height: 900 } });
  const cssResponsePromise = page.waitForResponse((response) =>
    response.url().endsWith(`${mountPath}/site/styles.css`),
  );
  const heroImageResponsePromise = page.waitForResponse((response) =>
    /\/careeros-workspace-\d+\.avif$/.test(response.url()),
  );
  const navigationResponse = await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  const cssResponse = await cssResponsePromise;
  const heroImageResponse = await heroImageResponsePromise;

  assert.equal(navigationResponse?.status(), 200, "Portfolio document must load successfully");
  assert.equal(cssResponse.status(), 200, "Portfolio stylesheet must load successfully");
  assert.match(
    cssResponse.headers()["content-type"] ?? "",
    /^text\/css\b/,
    "Portfolio stylesheet must be served with a CSS MIME type",
  );
  assert.equal(heroImageResponse.status(), 200, "Responsive hero image must load successfully");
  assert.match(
    heroImageResponse.headers()["content-type"] ?? "",
    /^image\/avif\b/,
    "Responsive hero image must be served with an AVIF MIME type",
  );

  const styleState = await page.evaluate(() => {
    const linkedSheet = Array.from(document.styleSheets).find((sheet) =>
      sheet.href?.endsWith("/careeros-local/site/styles.css"),
    );
    return {
      bodyMargin: getComputedStyle(document.body).margin,
      linkedRuleCount: linkedSheet ? linkedSheet.cssRules.length : 0,
    };
  });
  assert.equal(
    styleState.bodyMargin,
    "0px",
    "Portfolio stylesheet must reset the browser body margin",
  );
  assert(styleState.linkedRuleCount > 0, "Portfolio stylesheet must expose parsed CSS rules");

  assert.equal(await page.locator("h1").count(), 1, "Portfolio must expose exactly one h1");
  assert.equal(
    await page.locator("video[controls]").count(),
    1,
    "Portfolio must keep one controlled product demo",
  );
  assert(
    (await page
      .locator('a[href="https://github.com/ejupi-djenis30/careeros-local/releases/latest"]')
      .count()) >= 1,
    "Portfolio must link to the latest CareerOS release",
  );
  assert.equal(
    await page.getByRole("link", { name: "View source for CareerOS Local on GitHub" }).count(),
    1,
    "The source link accessible name must retain its visible label",
  );
  assert.equal(
    await page.locator('picture source[type="image/avif"]').count(),
    4,
    "Every product screenshot must expose an AVIF source",
  );
  assert.equal(
    await page.locator('picture source[type="image/webp"]').count(),
    4,
    "Every product screenshot must expose a WebP source",
  );
  assert.equal(
    await page.locator("video").getAttribute("poster"),
    "assets/careeros-demo-poster.webp",
    "The product tour poster must use a modern image format",
  );

  const robotsResponse = await page.request.get(`${baseUrl}robots.txt`);
  assert.equal(robotsResponse.status(), 200, "robots.txt must be published");
  assert.equal(
    await robotsResponse.text(),
    "User-agent: *\nAllow: /\n",
    "robots.txt must expose the intended crawler policy",
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
      const viewportWidth = document.documentElement.clientWidth;
      const boxes = selectors.flatMap((selector) => {
        const elements = Array.from(document.querySelectorAll(selector));
        if (elements.length === 0) return [{ selector, index: 0, missing: true }];
        return elements.map((element, index) => {
          const bounds = element.getBoundingClientRect();
          return {
            selector,
            index,
            missing: false,
            left: bounds.left,
            right: bounds.right,
            width: bounds.width,
            height: bounds.height,
          };
        });
      });
      const privacy = document.querySelector(".privacy-float")?.getBoundingClientRect();
      return {
        viewportWidth,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        boxes,
        privacyRightGap: privacy ? viewportWidth - privacy.right : null,
      };
    }, measuredSelectors);

    assert.equal(
      report.documentWidth,
      report.viewportWidth,
      `${width}px: document must not scroll horizontally`,
    );
    assert.equal(
      report.bodyWidth,
      report.viewportWidth,
      `${width}px: body must not scroll horizontally`,
    );

    for (const box of report.boxes) {
      const label = `${box.selector}[${box.index}]`;
      assert.equal(box.missing, false, `${width}px: missing ${label}`);
      assert(box.width > 0 && box.height > 0, `${width}px: ${label} must have visible geometry`);
      assert(box.left >= -1, `${width}px: ${label} crosses the left viewport edge (${box.left})`);
      assert(
        box.right <= report.viewportWidth + 1,
        `${width}px: ${label} crosses the right viewport edge (${box.right} > ${report.viewportWidth})`,
      );
    }

    assert(
      report.privacyRightGap >= 16,
      `${width}px: privacy badge needs a 16px viewport gutter (received ${report.privacyRightGap})`,
    );
  }

  const mobilePage = await browser.newPage({ viewport: { width: 375, height: 900 } });
  try {
    await mobilePage.goto(baseUrl, { waitUntil: "domcontentloaded" });
    const screenshots = mobilePage.locator("picture img");
    assert.equal(
      await screenshots.count(),
      4,
      "The responsive site must retain all four real product screenshots",
    );
    for (let index = 0; index < (await screenshots.count()); index += 1) {
      const screenshot = screenshots.nth(index);
      await screenshot.scrollIntoViewIfNeeded();
      await screenshot.evaluate((image) => image.decode());
      const state = await screenshot.evaluate((image) => ({
        complete: image.complete,
        currentSrc: image.currentSrc,
        naturalWidth: image.naturalWidth,
      }));
      assert.equal(state.complete, true, `Mobile screenshot ${index + 1} must finish loading`);
      assert.match(
        state.currentSrc,
        /-480\.avif$/,
        `Mobile screenshot ${index + 1} must select its 480px AVIF candidate`,
      );
      assert(
        state.naturalWidth > 0 && state.naturalWidth <= 480,
        `Mobile screenshot ${index + 1} must decode within its responsive width`,
      );
    }
  } finally {
    await mobilePage.close();
  }

  console.log(`Responsive portfolio validation passed at ${widths.length} viewport widths.`);
} finally {
  await browser.close();
  await closeServer(server);
}
