// UI-016: render the demonstration video shipped in kit/.uak/media/.
// scenes.html draws every frame as a pure function of t; this takes one screenshot per frame, encodes H.264 with
// ffmpeg, writes the poster JPEG and the WebVTT captions (English and Spanish share captions.json's timings).
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "playwright-core";

const here = dirname(fileURLToPath(import.meta.url));
const media = join(here, "..", "..", "kit", ".uak", "media");
const frames = join(here, "out", "frames");
const FPS = 10;
const POSTER_T = 2.6;

function stamp(s) {
  const ms = Math.round(s * 1000);
  const pad = (n, w) => String(n).padStart(w, "0");
  return pad(Math.floor(ms / 3600000), 2) + ":" + pad(Math.floor(ms / 60000) % 60, 2) + ":" +
    pad(Math.floor(ms / 1000) % 60, 2) + "." + pad(ms % 1000, 3);
}
function vtt(cues, lang) {
  return "WEBVTT\n\n" + cues.map((c, i) => `${i + 1}\n${stamp(c.start)} --> ${stamp(c.end)}\n${c[lang]}\n`).join("\n");
}
function ffmpeg(args) {
  const r = spawnSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", ...args], { stdio: "inherit" });
  if (r.status !== 0) throw new Error("ffmpeg failed: " + args.join(" "));
}

mkdirSync(media, { recursive: true });
rmSync(join(here, "out"), { recursive: true, force: true });
mkdirSync(frames, { recursive: true });
const cues = JSON.parse(readFileSync(join(here, "captions.json"), "utf8"));
for (const lang of ["en", "es"]) writeFileSync(join(media, `tutorial-${lang}.vtt`), vtt(cues, lang));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
await page.goto(pathToFileURL(join(here, "scenes.html")).href);
const duration = await page.evaluate(() => window.DURATION);
const total = Math.round(duration * FPS);
for (let i = 0; i < total; i++) {
  await page.evaluate((t) => window.seek(t), i / FPS);
  await page.screenshot({ path: join(frames, `f${String(i).padStart(5, "0")}.png`) });
  if (i % 100 === 0) console.log(`frame ${i}/${total}`);
}
await page.evaluate((t) => window.seek(t), POSTER_T);
await page.screenshot({ path: join(here, "out", "poster.png") });
await browser.close();

ffmpeg(["-framerate", String(FPS), "-i", join(frames, "f%05d.png"), "-c:v", "libx264", "-preset", "veryslow",
  "-tune", "animation", "-crf", "23", "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart", "-an",
  join(media, "tutorial.mp4")]);
ffmpeg(["-i", join(here, "out", "poster.png"), "-q:v", "5", join(media, "tutorial-poster.jpg")]);
for (const f of ["tutorial.mp4", "tutorial-poster.jpg", "tutorial-en.vtt", "tutorial-es.vtt"]) {
  console.log(`${f}: ${statSync(join(media, f)).size} bytes`);
}
