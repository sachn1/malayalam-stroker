/**
 * demo.js — interactive demo for malayalam-stroker.
 *
 * Loads glyph-data.json + stroke-data.json at startup, then wires up the
 * trace form, suggestion chips, replay button, and the stroke-library
 * drag-and-drop loader.
 */

import { createStrokeWriter, STROKE_LIBRARY } from "../js/src/index.js";

const writer = createStrokeWriter(document.getElementById("stage"));
const form = document.getElementById("traceForm");
const input = document.getElementById("wordInput");
const status = document.getElementById("status");
const btn = document.getElementById("traceBtn");

// Load bundled glyph data once — no server or font needed at runtime.
await writer.load("../js/src/glyph-data.json");
// Load hand-authored stroke paths if available (silent no-op if absent).
await writer.loadStrokes("../js/src/stroke-data.json");

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
