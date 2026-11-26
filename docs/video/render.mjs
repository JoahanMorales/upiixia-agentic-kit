// UAK-199: render the tutorial shipped in kit/.uak/media/ from scenes.html.
// scenes.html draws every frame as a pure function of t with the kit's own stylesheets (setup.html, dash.html) and fonts
// (kit/.uak/bin/lib/fonts). This script serves those files from disk to headless Chromium under a made-up origin and
// refuses every other request, so a render never touches the network; it takes one screenshot per frame, encodes H.264
// with ffmpeg (fixed thread count: the same frames give the same file), writes the poster JPEG, three small PNG frames
// extracted from the encoded video (the palette test reads them without ffmpeg) and the WebVTT captions.
//   node render.mjs                 the whole render (npm run render)
//   node render.mjs --still 42 out.png   one frame, to look at a scene while drawing it
//   node render.mjs --readme DIR    the README assets (banner, loop, stills) from the same drawing (npm run readme)
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, extname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { deflateSync } from "node:zlib";
import { chromium } from "playwright-core";

const here = dirname(fileURLToPath(import.meta.url));
const repo = normalize(join(here, "..", ".."));
const media = join(repo, "kit", ".uak", "media");
const out = join(here, "out");
const frames = join(out, "frames");
const FPS = 10;
const POSTER_T = 2.0;                 // the title: a designed frame, readable at the 560 px the setup page shows it
const FRAME_T = [11.0, 45.5, 58.5];   // the palette test's frames: a wizard screen, the crew, the dashboard
const LIMITS = { "tutorial.mp4": 820642, "tutorial-poster.jpg": 38328 };   // the sizes of v6.8: never heavier
const ORIGIN = "http://tutorial.uak.invalid";
const TYPES = { ".html": "text/html; charset=utf-8", ".woff2": "font/woff2", ".js": "text/javascript", ".css": "text/css" };

function stamp(s) {
  const ms = Math.round(s * 1000);
  const pad = (n, w) => String(n).padStart(w, "0");
  return pad(Math.floor(ms / 3600000), 2) + ":" + pad(Math.floor(ms / 60000) % 60, 2) + ":" +
    pad(Math.floor(ms / 1000) % 60, 2) + "." + pad(ms % 1000, 3);
}
function vtt(cues, lang) {
  return "WEBVTT\n\n" + cues.map((c, i) => `${i + 1}\n${stamp(c.start)} --> ${stamp(c.end)}\n${c[lang]}\n`).join("\n");
}
function ffmpeg(args, opts = {}) {
  const r = spawnSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", ...args], { stdio: opts.capture ? ["ignore", "pipe", "inherit"] : "inherit", maxBuffer: 64 << 20 });
  if (r.status !== 0) throw new Error("ffmpeg failed: " + args.join(" "));
  return r.stdout;
}
// A PNG written here, not by ffmpeg, so it can say where it comes from (a tEXt chunk the test reads).
function png(width, height, rgb, text) {
  const crcTable = Array.from({ length: 256 }, (_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
  const crc = (buf) => { let c = 0xffffffff; for (const b of buf) c = crcTable[(c ^ b) & 255] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
  const chunk = (type, data) => {
    const head = Buffer.alloc(8); head.writeUInt32BE(data.length, 0); head.write(type, 4, "latin1");
    const tail = Buffer.alloc(4); tail.writeUInt32BE(crc(Buffer.concat([head.subarray(4), data])), 0);
    return Buffer.concat([head, data, tail]);
  };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(width, 0); ihdr.writeUInt32BE(height, 4); ihdr.set([8, 2, 0, 0, 0], 8);
  const stride = width * 3, raw = Buffer.alloc((stride + 1) * height);
  for (let y = 0; y < height; y++) {            // filter Up: flat interfaces compress well and decode simply
    raw[y * (stride + 1)] = 2;
    for (let i = 0; i < stride; i++) raw[y * (stride + 1) + 1 + i] = (rgb[y * stride + i] - (y ? rgb[(y - 1) * stride + i] : 0)) & 255;
  }
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk("IHDR", ihdr),
    chunk("tEXt", Buffer.from("Source\0" + text, "latin1")), chunk("IDAT", deflateSync(raw, { level: 9 })), chunk("IEND", Buffer.alloc(0))]);
}

async function open() {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1, locale: "en-US",
    timezoneId: "UTC", colorScheme: "light", reducedMotion: "reduce" });
  const refused = [];
  // Only files of this repository, under the made-up origin; anything else is refused and fails the render.
  await context.route("**/*", (route) => {
    const url = new URL(route.request().url());
    const path = normalize(join(repo, decodeURIComponent(url.pathname)));
    if (url.origin !== ORIGIN || !path.startsWith(repo + sep)) { refused.push(route.request().url()); return route.abort(); }
    try {
      return route.fulfill({ status: 200, body: readFileSync(path), contentType: TYPES[extname(path)] || "application/octet-stream" });
    } catch (e) { refused.push(route.request().url()); return route.abort(); }
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => { throw e; });
  await page.goto(ORIGIN + "/docs/video/scenes.html");
  await page.evaluate(() => window.ready);
  const check = () => { if (refused.length) throw new Error("a request left the repository: " + refused.join(", ")); };
  return { browser, page, check };
}
async function shot(page, t, path) {
  await page.evaluate((x) => window.seek(x), t);
  await page.screenshot({ path, animations: "disabled", caret: "hide" });
}

const args = process.argv.slice(2);
if (args[0] === "--readme") {
  // The README's assets, in dark, from the same scenes.html: a 1280x640 banner whose eyebrow carries the major.minor of
  // kit/.uak/VERSION (read now, as scripts/make_media.py does), an 8 s loop of the parallel moment as animated WebP and
  // GIF with a still fallback, and two stills (the crew, the lanes into main).
  const dir = args[1] || join(out, "readme");
  mkdirSync(dir, { recursive: true });
  const version = readFileSync(join(repo, "kit", ".uak", "VERSION"), "utf8").trim().split(".").slice(0, 2).join(".");
  const { browser, page, check } = await open();
  await page.setViewportSize({ width: 1280, height: 640 });
  await page.evaluate((v) => window.EXTRA.banner(v), version);
  await page.screenshot({ path: join(dir, "banner.png") });
  await page.setViewportSize({ width: 1280, height: 720 });
  // the stills are cropped to what they show (the video keeps room at the bottom for its captions)
  await page.evaluate((t) => window.seek(t), POSTER_T);
  await page.screenshot({ path: join(dir, "crew.png"), clip: { x: 0, y: 0, width: 1280, height: 640 } });
  await page.evaluate((t) => window.seek(t), 49.6);
  await page.screenshot({ path: join(dir, "lanes-into-main.png"), clip: { x: 0, y: 0, width: 1280, height: 600 } });
  const lf = join(out, "loop"); rmSync(lf, { recursive: true, force: true }); mkdirSync(lf, { recursive: true });
  const LFPS = 12, len = await page.evaluate(() => window.EXTRA.LOOP_LEN);
  for (let i = 0; i < len * LFPS; i++) {
    await page.evaluate((t) => window.EXTRA.loop(t), i / LFPS);
    await page.screenshot({ path: join(lf, `l${String(i).padStart(4, "0")}.png`), animations: "disabled" });
  }
  await page.evaluate((t) => window.EXTRA.loop(t), 5.0);
  await page.screenshot({ path: join(dir, "parallel-loop-still.png") });
  check();
  await browser.close();
  const src = ["-framerate", String(LFPS), "-i", join(lf, "l%04d.png")];
  ffmpeg([...src, "-vf", "scale=960:540:flags=lanczos", "-c:v", "libwebp_anim", "-lossless", "0", "-q:v", "70", "-compression_level", "6", "-loop", "0", join(dir, "parallel-loop.webp")]);
  ffmpeg([...src, "-filter_complex", "scale=800:450:flags=lanczos,split[a][b];[a]palettegen=max_colors=64:stats_mode=full[p];[b][p]paletteuse=dither=none", "-loop", "0", join(dir, "parallel-loop.gif")]);
  for (const f of ["banner.png", "crew.png", "lanes-into-main.png", "parallel-loop.webp", "parallel-loop.gif", "parallel-loop-still.png"]) console.log(`${f}: ${statSync(join(dir, f)).size} bytes`);
  console.log(`banner eyebrow: v${version} · multi-agent orchestration`);
  process.exit(0);
}
if (args[0] === "--still") {
  const { browser, page, check } = await open();
  await shot(page, Number(args[1]), args[2] || join(here, "still.png"));
  check();
  await browser.close();
  process.exit(0);
}

mkdirSync(media, { recursive: true });
rmSync(out, { recursive: true, force: true });
mkdirSync(frames, { recursive: true });
const cues = JSON.parse(readFileSync(join(here, "captions.json"), "utf8"));
for (const lang of ["en", "es"]) writeFileSync(join(media, `tutorial-${lang}.vtt`), vtt(cues, lang));

const { browser, page, check } = await open();
const duration = await page.evaluate(() => window.DURATION);
const total = Math.round(duration * FPS);
for (let i = 0; i < total; i++) {
  await shot(page, i / FPS, join(frames, `f${String(i).padStart(5, "0")}.png`));
  if (i % 100 === 0) console.log(`frame ${i}/${total}`);
}
await shot(page, POSTER_T, join(out, "poster.png"));
check();
await browser.close();

const mp4 = join(media, "tutorial.mp4");
ffmpeg(["-framerate", String(FPS), "-i", join(frames, "f%05d.png"), "-c:v", "libx264", "-preset", "veryslow", "-tune", "animation",
  "-crf", "29", "-threads", "4", "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart", "-an",
  "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact", mp4]);
// The poster: the best JPEG quality that stays under the size of v6.8.
const poster = join(media, "tutorial-poster.jpg");
for (let q = 2; q <= 12; q++) {
  ffmpeg(["-i", join(out, "poster.png"), "-q:v", String(q), "-pix_fmt", "yuvj420p", "-fflags", "+bitexact", "-flags:v", "+bitexact", poster]);
  if (statSync(poster).size <= LIMITS["tutorial-poster.jpg"]) break;
}
// Three frames of the encoded video, 320x180, each saying which video and which second it comes from.
const sha = createHash("sha256").update(readFileSync(mp4)).digest("hex");
FRAME_T.forEach((t, i) => {
  const rgb = ffmpeg(["-i", mp4, "-ss", t.toFixed(1), "-frames:v", "1", "-vf", "scale=320:180:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], { capture: true });
  if (rgb.length !== 320 * 180 * 3) throw new Error(`frame at ${t} s: ${rgb.length} bytes`);
  writeFileSync(join(media, `tutorial-frame-${i + 1}.png`), png(320, 180, rgb, `tutorial.mp4 sha256=${sha} t=${t.toFixed(1)}`));
});
let over = false;
for (const f of ["tutorial.mp4", "tutorial-poster.jpg", "tutorial-en.vtt", "tutorial-es.vtt", "tutorial-frame-1.png", "tutorial-frame-2.png", "tutorial-frame-3.png"]) {
  const size = statSync(join(media, f)).size;
  console.log(`${f}: ${size} bytes`);
  if (LIMITS[f] && size > LIMITS[f]) { over = true; console.error(`${f} is heavier than v6.8 (${LIMITS[f]} bytes)`); }
}
console.log(`duration: ${duration} s, ${total} frames at ${FPS} fps`);
if (over || duration > 75) process.exit(1);
