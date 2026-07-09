/**
 * demo.js — interactive demo for malayalam-stroker.
 *
 * Loads glyph-data.json + stroke-data.json at startup, then wires up the
 * trace form, suggestion chips, replay button, and the stroke-library
 * drag-and-drop loader.
 */

import { createStrokeWriter, STROKE_LIBRARY } from "../js/src/index.js";

// Fetch + parse glyph-data.json once and hand the same parsed object to every
// writer instance (main stage + logo) via the `glyphData` option — each
// writer's own load() would otherwise independently re-fetch and, worse,
// re-parse this file, and at its current (prototype-stage) size that
// double parse is a real, noticeable chunk of page-load time.
const glyphDataResp = await fetch("../js/src/glyph-data.json");
const glyphData = await glyphDataResp.json();

const writer = createStrokeWriter(document.getElementById("stage"), { glyphData });
const form = document.getElementById("traceForm");
const input = document.getElementById("wordInput");
const status = document.getElementById("status");
const btn = document.getElementById("traceBtn");

// Load stroke-data.json (processed: centered + smoothed + ghost-straightened +
// expanded — see tools/process_strokes.py) first, then stroke-data.raw.json —
// loadStrokes() never overwrites a cluster already in STROKE_LIBRARY, so this
// fills in any newly hand-drawn characters that haven't been through the
// pipeline yet, without ever showing stale data for ones that have.
await writer.loadStrokes(`../js/src/stroke-data.json?v=${Date.now()}`);
await writer.loadStrokes(`../js/src/stroke-data.raw.json?v=${Date.now()}`);

// ---------------------------------------------------------------------------
// Logo — the app showcases itself by animating its own Malayalam name.
// Runs independently of the main writer so it doesn't delay the word trace.
//
// Two-stage reveal: the black outline traces first with the violet fill
// hidden, then once the outline is complete the fill sweeps in left-to-right.
// `outlineOnly` forces the ghost-outline trace for every glyph in the word,
// ignoring the shared STROKE_LIBRARY, so ജ/യ/ശ്രീ all animate in the same
// outline style instead of mixing authored centerline strokes with fallback.
// ---------------------------------------------------------------------------

const logoStage = document.getElementById("logo-stage");
if (logoStage) {
  const logoWriter = createStrokeWriter(logoStage, { glyphData, speed: 42000, outlineOnly: true });

  /**
   * Play (or replay) the logo, holding the ghost's violet fill hidden via an
   * SVG clip-path until the black outline trace finishes, then animating the
   * clip rect's width to sweep the fill in left-to-right.
   *
   * `buildStage()` runs synchronously inside `play()`/`replay()` before their
   * first `await`, so the ghost element already exists in the DOM by the
   * time the call returns — that's what lets us grab and clip it here
   * without waiting for the trace to finish.
   *
   * @param {() => Promise<void>} trigger
   */
  async function playLogoWithReveal(trigger) {
    const tracePromise = trigger();
    const svg = logoStage.querySelector("svg");
    const ghost = svg?.querySelector(".ms-ghost");
    let clipRect = null;

    if (ghost) {
      const bbox = ghost.getBBox();
      const svgns = "http://www.w3.org/2000/svg";
      const clipPath = document.createElementNS(svgns, "clipPath");
      clipPath.id = "logo-reveal-clip";
      clipRect = document.createElementNS(svgns, "rect");
      clipRect.setAttribute("x", String(bbox.x));
      clipRect.setAttribute("y", String(bbox.y - 4));
      clipRect.setAttribute("width", "0");
      clipRect.setAttribute("height", String(bbox.height + 8));
      clipPath.appendChild(clipRect);
      svg.appendChild(clipPath);
      ghost.setAttribute("clip-path", "url(#logo-reveal-clip)");
    }

    await tracePromise;

    if (clipRect) {
      const bbox = ghost.getBBox();
      const duration = 650;
      const start = performance.now();
      const step = (now) => {
        const t = Math.min(1, (now - start) / duration);
        const eased = 1 - (1 - t) ** 3;
        clipRect.setAttribute("width", String(bbox.width * eased));
        if (t < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }
  }

  // glyphData is already supplied above, so play() resolves it synchronously
  // (no fetch of its own) — no separate load() step needed here.
  playLogoWithReveal(() => logoWriter.play("ജയശ്രീ"));
  logoStage.addEventListener("click", () => playLogoWithReveal(() => logoWriter.replay()));
}

// ---------------------------------------------------------------------------
// Trace
// ---------------------------------------------------------------------------

/**
 * Trace the given word and handle errors.
 *
 * @param {string} word
 */
async function traceWord(word) {
  word = word.trim();
  if (!word) return;
  status.textContent = "";
  btn.disabled = true;
  try {
    await writer.play(word);
  } catch (err) {
    status.textContent = err.message;
  } finally {
    btn.disabled = false;
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  traceWord(input.value);
});

document.querySelectorAll(".chips button").forEach((b) =>
  b.addEventListener("click", () => {
    input.value = b.dataset.word;
    traceWord(input.value);
  })
);

document.getElementById("replay").addEventListener("click", () => writer.replay());

// ---------------------------------------------------------------------------
// Stroke library drag-and-drop
// ---------------------------------------------------------------------------

const libDrop = document.getElementById("lib-drop");
const libFile = document.getElementById("lib-file");
const libStatus = document.getElementById("lib-status");

/**
 * Merge a stroke-data JSON file into the active STROKE_LIBRARY and replay.
 *
 * @param {File} file
 */
function loadLibrary(file) {
  const reader = new FileReader();
  reader.onload = (ev) => {
    try {
      const data = JSON.parse(ev.target.result);
      const count = Object.keys(data).length;
      Object.assign(STROKE_LIBRARY, data);
      libStatus.textContent = `✓ Loaded ${count} glyph${count !== 1 ? "s" : ""} — replay to see authored strokes`;
      libDrop.style.borderColor = "#6d28d9";
      writer.replay();
    } catch {
      libStatus.textContent = "Could not parse JSON — is this a stroke-data export?";
    }
  };
  reader.readAsText(file);
}

libDrop.addEventListener("click", () => libFile.click());
libFile.addEventListener("change", () => libFile.files[0] && loadLibrary(libFile.files[0]));
libDrop.addEventListener("dragover", (e) => {
  e.preventDefault();
  libDrop.style.borderColor = "#6d28d9";
});
libDrop.addEventListener("dragleave", () => {
  libDrop.style.borderColor = "#c4b5e8";
});
libDrop.addEventListener("drop", (e) => {
  e.preventDefault();
  libDrop.style.borderColor = "#c4b5e8";
  if (e.dataTransfer.files[0]) loadLibrary(e.dataTransfer.files[0]);
});

// Trace the default word on load.
traceWord(input.value);
