/** Render and validate the native CareerOS editorial SVG assets. */

import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const requireFromFrontend = createRequire(resolve(repositoryRoot, "frontend", "package.json"));
const { chromium } = requireFromFrontend("playwright");

const assets = [
  {
    source: "docs/assets/careeros-local-hero.svg",
    output: "docs/assets/careeros-local-hero.png",
    width: 1774,
    height: 887,
  },
  {
    source: "docs/assets/devpost-thumbnail.svg",
    output: "docs/assets/devpost-thumbnail.png",
    width: 1200,
    height: 1200,
  },
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function readPngDimensions(buffer) {
  const signature = "89504e470d0a1a0a";
  assert(buffer.subarray(0, 8).toString("hex") === signature, "Output is not a PNG file");
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
}

function validateSource(svg, asset) {
  const viewBox = `viewBox="0 0 ${asset.width} ${asset.height}"`;
  assert(svg.includes(viewBox), `${asset.source}: expected ${viewBox}`);
  assert(!/<(?:image|script|foreignObject)\b/i.test(svg), `${asset.source}: embedded or executable content is forbidden`);
  assert(
    !/(?:href|src)=["'](?:https?:|data:|file:)/i.test(svg) && !/url\(["']?(?!#)/i.test(svg),
    `${asset.source}: external and embedded resources are forbidden`,
  );
  assert(!/<text\b/i.test(svg), `${asset.source}: text would make rendering font-dependent`);
  assert((svg.match(/data-quadrant=/g) || []).length === 4, `${asset.source}: exactly four mirrored quadrants are required`);
}

function near(left, right, tolerance = 0.02) {
  return Math.abs(left - right) <= tolerance;
}

async function validateGeometry(page, asset) {
  const geometry = await page.evaluate(() => {
    const bounds = (selector) => {
      const node = document.querySelector(selector);
      if (!node) throw new Error(`Missing ${selector}`);
      const box = node.getBoundingClientRect();
      return { x: box.x, y: box.y, width: box.width, height: box.height };
    };
    return {
      canvas: bounds("svg"),
      frame: bounds("[data-frame]"),
      center: bounds("[data-center]"),
      quadrants: Object.fromEntries(
        [...document.querySelectorAll("[data-quadrant]")].map((node) => {
          const box = node.getBoundingClientRect();
          return [node.getAttribute("data-quadrant"), { x: box.x, y: box.y, width: box.width, height: box.height }];
        }),
      ),
    };
  });

  const { width, height } = asset;
  const right = (box) => box.x + box.width;
  const bottom = (box) => box.y + box.height;
  const centerX = (box) => box.x + box.width / 2;
  const centerY = (box) => box.y + box.height / 2;

  assert(near(geometry.canvas.width, width) && near(geometry.canvas.height, height), `${asset.source}: SVG viewport overflow`);
  assert(near(geometry.frame.x, width - right(geometry.frame)), `${asset.source}: frame horizontal margins differ`);
  assert(near(geometry.frame.y, height - bottom(geometry.frame)), `${asset.source}: frame vertical margins differ`);
  assert(near(centerX(geometry.center), width / 2), `${asset.source}: center panel is off the horizontal axis`);
  assert(near(centerY(geometry.center), height / 2), `${asset.source}: center panel is off the vertical axis`);

  const q = geometry.quadrants;
  for (const name of ["top-left", "top-right", "bottom-left", "bottom-right"]) {
    assert(q[name], `${asset.source}: missing ${name} quadrant`);
    assert(q[name].x >= 0 && q[name].y >= 0 && right(q[name]) <= width && bottom(q[name]) <= height, `${asset.source}: ${name} quadrant overflows`);
  }
  assert(near(q["top-left"].x, width - right(q["top-right"])), `${asset.source}: top quadrants are not mirrored horizontally`);
  assert(near(q["bottom-left"].x, width - right(q["bottom-right"])), `${asset.source}: bottom quadrants are not mirrored horizontally`);
  assert(near(q["top-left"].y, height - bottom(q["bottom-left"])), `${asset.source}: left quadrants are not mirrored vertically`);
  assert(near(q["top-right"].y, height - bottom(q["bottom-right"])), `${asset.source}: right quadrants are not mirrored vertically`);
  assert(near(q["top-left"].width, q["bottom-right"].width) && near(q["top-left"].height, q["bottom-right"].height), `${asset.source}: diagonal quadrant dimensions differ`);

  const mirrorDeltas = [
    Math.abs(q["top-left"].x - (width - right(q["top-right"]))),
    Math.abs(q["bottom-left"].x - (width - right(q["bottom-right"]))),
    Math.abs(q["top-left"].y - (height - bottom(q["bottom-left"]))),
    Math.abs(q["top-right"].y - (height - bottom(q["bottom-right"]))),
    Math.abs(q["top-left"].width - q["bottom-right"].width),
    Math.abs(q["top-left"].height - q["bottom-right"].height),
  ];
  const overflow = Math.max(
    0,
    ...Object.values(q).flatMap((box) => [-box.x, -box.y, right(box) - width, bottom(box) - height]),
  );

  return { ...geometry, maxMirrorDelta: Math.max(...mirrorDeltas), overflow };
}

const browser = await chromium.launch({ headless: true });
try {
  for (const asset of assets) {
    const sourcePath = resolve(repositoryRoot, asset.source);
    const outputPath = resolve(repositoryRoot, asset.output);
    const svg = await readFile(sourcePath, "utf8");
    validateSource(svg, asset);

    const page = await browser.newPage({
      viewport: { width: asset.width, height: asset.height },
      deviceScaleFactor: 1,
      colorScheme: "dark",
    });
    await page.setContent(
      `<!doctype html><html><head><style>html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#0a0d0b}svg{display:block}</style></head><body>${svg}</body></html>`,
      { waitUntil: "load" },
    );

    const geometry = await validateGeometry(page, asset);
    await page.screenshot({
      path: outputPath,
      clip: { x: 0, y: 0, width: asset.width, height: asset.height },
      animations: "disabled",
      caret: "hide",
      omitBackground: false,
      type: "png",
    });
    await page.close();

    const png = await readFile(outputPath);
    const dimensions = readPngDimensions(png);
    assert(dimensions.width === asset.width && dimensions.height === asset.height, `${asset.output}: rendered dimensions differ`);
    const digest = createHash("sha256").update(png).digest("hex");
    const horizontalMargin = geometry.frame.x;
    const verticalMargin = geometry.frame.y;
    console.log(`${asset.output} ${dimensions.width}x${dimensions.height} sha256=${digest}`);
    console.log(`  frame margins: ${horizontalMargin}px horizontal, ${verticalMargin}px vertical; center delta: 0px`);
    console.log(`  quadrant mirror max delta: ${geometry.maxMirrorDelta}px; overflow: ${geometry.overflow}px`);
  }
} finally {
  await browser.close();
}
