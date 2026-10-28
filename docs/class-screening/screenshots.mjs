// Renders the class screening mock-ups at desktop and phone width.
// The pages load the website theme from /site/, as analyser.html does, so
// this serves /site/ from a vahini-web checkout and the mock-ups beside it.
//
//   SITE_DIR=<vahini-web checkout>/site node docs/class-screening/screenshots.mjs
//
// Needs the playwright package (run it in mcr.microsoft.com/playwright).
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const HERE = dirname(fileURLToPath(import.meta.url));
const SITE = process.env.SITE_DIR;
if (!SITE) throw new Error("set SITE_DIR to a vahini-web checkout's site/ folder");
const TYPES = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".webp": "image/webp", ".woff2": "font/woff2", ".png": "image/png", ".svg": "image/svg+xml" };

const server = createServer(async (req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname));
  const file = path.startsWith("/site/") ? join(SITE, path.slice(6)) : join(HERE, path);
  try {
    const body = await readFile(file);
    res.writeHead(200, { "content-type": TYPES[extname(file)] || "application/octet-stream" });
    res.end(body);
  } catch {
    res.writeHead(404).end();
  }
}).listen(0);
const base = `http://127.0.0.1:${server.address().port}`;

const PAGES = ["01-pick", "02-running", "03-resume", "04-finished", "05-refused", "06-export"];
const SIZES = [["desktop", { width: 1440, height: 900 }, 1], ["phone", { width: 390, height: 844 }, 2]];
const browser = await chromium.launch();
for (const [name, viewport, scale] of SIZES) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: scale });
  for (const p of PAGES) {
    await page.goto(`${base}/${p}.html`, { waitUntil: "networkidle" });
    await page.evaluate(() => document.fonts.ready);
    // Phone pages are cut at three screens: the rest repeats the same rows.
    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    const clip = name === "phone" && height > 2400 ? { x: 0, y: 0, width: viewport.width, height: 2400 } : undefined;
    await page.screenshot({ path: join(HERE, "screens", `${p}-${name}.png`), fullPage: true, clip });
  }
  await page.close();
}
await browser.close();
server.close();
