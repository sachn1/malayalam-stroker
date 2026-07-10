/**
 * stroke-recorder.js — logic for the stroke recorder tool.
 *
 * Depends on:
 *   - A <div id="drop-zone"> with <input type="file" id="file-input">
 *   - A <div id="recorder"> containing #canvas-wrap, #glyph-label, nav buttons
 *   - A <div id="export-area"> with #export-output textarea and action buttons
 */

"use strict";

const SVGNS = "http://www.w3.org/2000/svg";

/** Catmull-Rom tension for live stroke preview. */
const TENSION = 0.4;

/** Minimum distance (font units) between recorded points. */
const MIN_DIST_RECORD = 6;

/** Minimum distance (font units) between live-preview points. */
const MIN_DIST_PREVIEW = 3;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

/** @type {{ unitsPerEm: number, ascent: number, descent: number, glyphs: object[] } | null} */
let trace = null;

/** @type {number} */
let glyphIndex = 0;

/** @type {SVGSVGElement | null} */
let drawingSvg = null;

/** @type {{ x: number, y: number }[] | null} */
let currentPts = null;

/** @type {SVGPathElement | null} */
let previewPath = null;

/**
 * Recorded strokes per cluster.
 *
 * @type {Record<string, { d: string }[]>}
 */
const strokeData = {};

/**
 * Existing stroke-data.raw.json loaded for merging at export time.
 *
 * @type {Record<string, { strokes: { d: string }[] }> | null}
 */
let existingStrokeData = null;

/**
 * Get `strokeData[clusterStr]`, seeding it from `existingStrokeData` the
 * first time a character with already-recorded strokes is touched (viewed,
 * drawn on, erased, or undone).
 *
 * Without this, navigating to an already-recorded character and drawing an
 * additional stroke would silently start from an empty array — the
 * existing strokes wouldn't show on the canvas, and worse, export would
 * overwrite them entirely with just the new stroke (export layers
 * `strokeData` over `existingStrokeData` per-cluster, not per-stroke — see
 * the export-btn handler).
 *
 * @param {string} clusterStr
 * @returns {{ d: string }[]}
 */
function ensureStrokes(clusterStr) {
  if (!strokeData[clusterStr]) {
    const existing = existingStrokeData?.[clusterStr]?.strokes;
    strokeData[clusterStr] = existing ? existing.map((s) => ({ d: s.d })) : [];
  }
  return strokeData[clusterStr];
}

/**
 * Per-cluster stack of strokes removed by Undo, restorable via Redo.
 * Cleared for a cluster whenever a new stroke is drawn, or its strokes are
 * cleared/erased — same rule as any standard undo/redo history.
 *
 * @type {Record<string, { d: string }[]>}
 */
const redoStacks = {};

/** Whether eraser mode is active. */
let eraserMode = false;

/** Eraser radius in font units. */
const ERASER_RADIUS = 30;

/** Whether the dropdown/nav show every glyph-data cluster instead of just the reduced atom set. */
let showAllClusters = false;

/**
 * Clusters added this session via "+ Add" — always treated as atoms
 * regardless of the reduced-set filter, so a deliberately-added new
 * combination is never hidden from its own recording session.
 *
 * @type {Set<string>}
 */
const manuallyAddedClusters = new Set();

/**
 * Compound vowel signs composed from simpler marks at runtime (see
 * js/src/index.js's SPLIT_VOWEL_PARTS) — never need their own recorded
 * stroke, so they're excluded from the atom set even though they are
 * single codepoints.
 */
const DEPRECATED_ATOMS = new Set(["ൊ", "ോ", "ൌ"]); // ൊ ോ ൌ

/**
 * Whether `clusterStr` belongs to the reduced "needs its own hand-drawn
 * stroke" atom set, as opposed to a combination that composes automatically
 * from other atoms at runtime (see README's "Composing combinations instead
 * of pre-shaping every one").
 *
 * Single codepoints (letters, digits, virama, matras) are always atoms —
 * they can't be decomposed further. A multi-character cluster is an atom
 * only if it's already known to need its own stroke: either it's already
 * recorded in the loaded stroke-data.raw.json (the existing 292-ish
 * hand-picked fused/conjunct forms), or it was just added this session via
 * "+ Add".
 *
 * @param {string} clusterStr
 * @returns {boolean}
 */
function isAtom(clusterStr) {
  if (DEPRECATED_ATOMS.has(clusterStr)) return false;
  if (clusterStr.length === 1) return true;
  if (manuallyAddedClusters.has(clusterStr)) return true;
  return !!existingStrokeData?.[clusterStr]?.strokes?.length;
}

/**
 * Indices into `trace.glyphs` currently visible, honouring `showAllClusters`.
 *
 * @returns {number[]}
 */
function visibleGlyphIndices() {
  if (!trace) return [];
  if (showAllClusters) return trace.glyphs.map((_, i) => i);
  const out = [];
  for (const [i, g] of trace.glyphs.entries()) {
    if (isAtom(g.clusterStr)) out.push(i);
  }
  return out;
}

// ---------------------------------------------------------------------------
// SVG helpers
// ---------------------------------------------------------------------------

/**
 * Create an SVG element with the given attributes.
 *
 * @param {string} tag - SVG element tag name.
 * @param {Record<string, string | number>} attrs - Attribute map.
 * @returns {SVGElement}
 */
function svgEl(tag, attrs) {
  const el = document.createElementNS(SVGNS, tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  return el;
}

/**
 * Convert a pointer event to SVG coordinate space (font units).
 *
 * @param {SVGSVGElement} svg
 * @param {PointerEvent | TouchEvent} e
 * @returns {{ x: number, y: number }}
 */
function toSvgPt(svg, e) {
  const pt = svg.createSVGPoint();
  const src = e.touches ? e.touches[0] : e;
  pt.x = src.clientX;
  pt.y = src.clientY;
  return pt.matrixTransform(svg.getScreenCTM().inverse());
}

// ---------------------------------------------------------------------------
// Stroke smoothing — Catmull-Rom → cubic bezier
// ---------------------------------------------------------------------------

/**
 * Round a number to the nearest integer for compact SVG output.
 *
 * @param {number} n
 * @returns {number}
 */
function r(n) {
  return Math.round(n);
}

/**
 * Remove points that are closer than minDist to reduce jitter.
 *
 * @param {{ x: number, y: number }[]} pts
 * @param {number} minDist
 * @returns {{ x: number, y: number }[]}
 */
function downsample(pts, minDist) {
  if (pts.length <= 2) return pts;
  const out = [pts[0]];
  for (let i = 1; i < pts.length - 1; i++) {
    const prev = out[out.length - 1];
    const dx = pts[i].x - prev.x;
    const dy = pts[i].y - prev.y;
    if (Math.sqrt(dx * dx + dy * dy) >= minDist) out.push(pts[i]);
  }
  out.push(pts[pts.length - 1]);
  return out;
}

/**
 * Convert a sequence of points to a smooth Catmull-Rom cubic bezier path.
 *
 * @param {{ x: number, y: number }[]} pts
 * @returns {string} SVG path `d` string.
 */
function smoothPath(pts) {
  if (pts.length < 2) return "";
  if (pts.length === 2) {
    return `M ${r(pts[0].x)} ${r(pts[0].y)} L ${r(pts[1].x)} ${r(pts[1].y)}`;
  }

  let d = `M ${r(pts[0].x)} ${r(pts[0].y)}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(i - 1, 0)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(i + 2, pts.length - 1)];
    const cp1x = p1.x + (p2.x - p0.x) * TENSION;
    const cp1y = p1.y + (p2.y - p0.y) * TENSION;
    const cp2x = p2.x - (p3.x - p1.x) * TENSION;
    const cp2y = p2.y - (p3.y - p1.y) * TENSION;
    d += ` C ${r(cp1x)} ${r(cp1y)} ${r(cp2x)} ${r(cp2y)} ${r(p2.x)} ${r(p2.y)}`;
  }
  return d;
}

// ---------------------------------------------------------------------------
// File loading
// ---------------------------------------------------------------------------

/**
 * Parse the loaded JSON and initialise the recorder.
 *
 * Accepts both glyph-data.json (preferred) and the legacy StrokeTrace format.
 *
 * @param {string} text - Raw JSON file contents.
 */
function parseGlyphData(text) {
  const parsed = JSON.parse(text);
  let unitsPerEm, ascent, descent, glyphs;

  if (parsed.meta && parsed.clusters) {
    ({ unitsPerEm, ascent, descent } = parsed.meta);
    glyphs = Object.entries(parsed.clusters).map(([clusterStr, entry]) => ({
      clusterStr,
      paths: entry.glyphs,
      advance: entry.advance,
    }));
  } else {
    // Legacy StrokeTrace array from the Python CLI
    const sources = Array.isArray(parsed) ? parsed : [parsed];
    if (!sources[0]?.glyphs) {
      throw new Error("Not a recognised format (missing 'clusters' or 'glyphs')");
    }
    ({ unitsPerEm, ascent, descent } = sources[0]);
    const seen = new Set();
    glyphs = [];
    for (const src of sources) {
      for (const g of src.glyphs) {
        if (!seen.has(g.glyphName)) {
          seen.add(g.glyphName);
          glyphs.push({
            clusterStr: g.glyphName,
            paths: [{ d: g.d, x: 0, y: 0 }],
            advance: unitsPerEm * 0.85,
          });
        }
      }
    }
  }

  trace = { unitsPerEm, ascent, descent, glyphs };
  glyphIndex = 0;
  document.getElementById("drop-zone").classList.add("hidden");
  document.getElementById("recorder").classList.add("active");
  populateSelect();
  renderGlyph();
}

/**
 * Load a File object as text and hand it to parseGlyphData.
 *
 * @param {File} file
 */
function loadFile(file) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    try {
      parseGlyphData(ev.target.result);
    } catch (err) {
      alert("Could not load JSON: " + err.message);
    }
  };
  reader.readAsText(file);
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

/**
 * Whether `clusterStr` already has a recorded stroke, in this session or the
 * loaded stroke-data.raw.json.
 *
 * @param {string} clusterStr
 * @returns {boolean}
 */
function isRecorded(clusterStr) {
  if (strokeData[clusterStr]?.length) return true;
  return !!existingStrokeData?.[clusterStr]?.strokes?.length;
}

/**
 * Populate the jump-to dropdown with visible clusters (honouring the
 * reduced-set filter), each flagged with whether it's already recorded.
 */
function populateSelect() {
  const sel = document.getElementById("glyph-select");
  sel.innerHTML = "";
  const visible = visibleGlyphIndices();
  for (const [pos, i] of visible.entries()) {
    const g = trace.glyphs[i];
    const opt = document.createElement("option");
    opt.value = String(i);
    const mark = isRecorded(g.clusterStr) ? "✓" : "○";
    opt.textContent = `${mark} ${g.clusterStr}  ·  ${pos + 1} / ${visible.length}`;
    sel.appendChild(opt);
  }
  sel.value = String(glyphIndex);

  const status = document.getElementById("filter-status");
  if (status) {
    status.textContent = showAllClusters
      ? `showing all ${trace.glyphs.length}`
      : `${visible.length} atoms (of ${trace.glyphs.length} total clusters)`;
  }
}

/**
 * Return the advance width of glyph at index *idx*.
 *
 * @param {number} idx
 * @returns {number}
 */
function glyphWidth(idx) {
  return trace.glyphs[idx]?.advance ?? trace.unitsPerEm * 0.85;
}

/**
 * Parse the starting point from an SVG path `d` string.
 *
 * @param {string} d
 * @returns {{ x: number, y: number } | null}
 */
function getPathStart(d) {
  const m = d.match(/M\s*([-\d.]+)\s+([-\d.]+)/);
  return m ? { x: parseFloat(m[1]), y: parseFloat(m[2]) } : null;
}

/**
 * Re-render the current glyph's SVG, ghost, and recorded strokes.
 */
function renderGlyph() {
  const wrap = document.getElementById("canvas-wrap");
  const g = trace.glyphs[glyphIndex];
  const { unitsPerEm, ascent, descent } = trace;

  const pad = unitsPerEm * 0.12;
  const w = Math.max(glyphWidth(glyphIndex), unitsPerEm * 0.5);
  const vbX = -pad;
  const vbY = -(ascent + pad);
  const vbW = w + pad * 2;
  const vbH = ascent - descent + pad * 2;

  const svg = document.createElementNS(SVGNS, "svg");
  svg.setAttribute("viewBox", `${vbX} ${vbY} ${vbW} ${vbH}`);
  svg.style.cssText = "display:block; width:100%; max-height:300px;";

  // Ghost letterform — all sub-glyphs for this cluster
  for (const p of g.paths) {
    const ghost = svgEl("path", {
      d: p.d,
      fill: "#e0daf5",
      opacity: "0.5",
      stroke: "#c4b5e8",
      "stroke-width": unitsPerEm * 0.01,
      "fill-rule": "evenodd",
    });
    if (p.x || p.y) ghost.setAttribute("transform", `translate(${p.x},${p.y})`);
    svg.appendChild(ghost);
  }

  // Previously recorded strokes with numbered start-point badges — seeded
  // from existingStrokeData on first visit via ensureStrokes, so loaded
  // strokes actually show up here instead of only at export time.
  const strokes = ensureStrokes(g.clusterStr);
  for (const [idx, s] of strokes.entries()) {
    svg.appendChild(
      svgEl("path", {
        d: s.d,
        fill: "none",
        stroke: "#6d28d9",
        "stroke-width": unitsPerEm * 0.025,
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
      })
    );

    const startPt = getPathStart(s.d);
    if (startPt) {
      svg.appendChild(
        svgEl("circle", {
          cx: startPt.x,
          cy: startPt.y,
          r: unitsPerEm * 0.04,
          fill: "#6d28d9",
          opacity: "0.85",
        })
      );
      const label = svgEl("text", {
        x: startPt.x,
        y: startPt.y,
        "text-anchor": "middle",
        "dominant-baseline": "central",
        fill: "white",
        "font-size": unitsPerEm * 0.06,
        "font-weight": "bold",
        "font-family": "system-ui",
      });
      label.textContent = String(idx + 1);
      svg.appendChild(label);
    }
  }

  wrap.innerHTML = "";
  wrap.appendChild(svg);
  drawingSvg = svg;
  previewPath = null;
  currentPts = null;

  const visible = visibleGlyphIndices();
  const pos = visible.indexOf(glyphIndex);
  const posLabel = pos === -1 ? `${glyphIndex + 1} / ${trace.glyphs.length}` : `${pos + 1} / ${visible.length}`;
  const recorded = isRecorded(g.clusterStr);
  const statusLabel = recorded
    ? `<span class="status-recorded">✓ already recorded</span>`
    : `<span class="status-missing">○ needs a stroke</span>`;
  document.getElementById("glyph-label").innerHTML =
    `<strong>${g.clusterStr}</strong> &nbsp;·&nbsp; ${posLabel} &nbsp;·&nbsp; ${statusLabel}`;

  // Sync dropdown selection
  const sel = document.getElementById("glyph-select");
  sel.value = String(glyphIndex);

  updateCounts();

  document.getElementById("prev-btn").disabled = pos <= 0;
  document.getElementById("next-btn").disabled = pos === -1 || pos === visible.length - 1;

  svg.addEventListener("pointerdown", onPointerDown);
  svg.addEventListener("pointermove", onPointerMove);
  svg.addEventListener("pointerup", onPointerUp);
  svg.addEventListener("pointercancel", onPointerUp);
}

/**
 * Refresh the stroke counter and undo/redo-button state.
 */
function updateCounts() {
  const g = trace.glyphs[glyphIndex];
  const n = ensureStrokes(g.clusterStr).length;
  document.getElementById("stroke-count").textContent =
    `${n} stroke${n !== 1 ? "s" : ""} recorded`;
  document.getElementById("undo-btn").disabled = n === 0;
  document.getElementById("redo-btn").disabled = (redoStacks[g.clusterStr]?.length ?? 0) <= 0;
}

// ---------------------------------------------------------------------------
// Eraser helpers
// ---------------------------------------------------------------------------

/**
 * Parse a smooth SVG path `d` back into sample points for erasing.
 *
 * @param {string} d
 * @returns {{ x: number, y: number }[]}
 */
function samplePathPoints(d) {
  const pts = [];
  const re = /([MLCS])\s*([-\d.]+(?:\s+[-\d.]+)*)/gi;
  let m;
  while ((m = re.exec(d))) {
    const cmd = m[1].toUpperCase();
    const nums = m[2].trim().split(/\s+/).map(Number);
    if (cmd === "M" || cmd === "L") {
      pts.push({ x: nums[0], y: nums[1] });
    } else if (cmd === "C") {
      // Only take the endpoint of each cubic
      pts.push({ x: nums[4], y: nums[5] });
    }
  }
  return pts;
}

/**
 * Erase points near (ex, ey) from all recorded strokes of the current glyph.
 * Strokes that get split produce multiple new strokes.
 *
 * @param {number} ex - Eraser X in font units
 * @param {number} ey - Eraser Y in font units
 */
function eraseAt(ex, ey) {
  const g = trace.glyphs[glyphIndex];
  const strokes = ensureStrokes(g.clusterStr);
  if (strokes.length === 0) return;

  const r2 = ERASER_RADIUS * ERASER_RADIUS;
  const newStrokes = [];

  for (const stroke of strokes) {
    const pts = samplePathPoints(stroke.d);
    // Split into runs of points that are outside the eraser
    let run = [];
    const runs = [];
    for (const p of pts) {
      const dx = p.x - ex;
      const dy = p.y - ey;
      if (dx * dx + dy * dy < r2) {
        if (run.length >= 2) runs.push(run);
        run = [];
      } else {
        run.push(p);
      }
    }
    if (run.length >= 2) runs.push(run);

    for (const r of runs) {
      newStrokes.push({ d: smoothPath(r) });
    }
  }

  strokeData[g.clusterStr] = newStrokes;
  redoStacks[g.clusterStr] = [];
}

/** @type {SVGCircleElement | null} */
let eraserCursor = null;

// ---------------------------------------------------------------------------
// Drawing event handlers
// ---------------------------------------------------------------------------

/**
 * Handle pointer-down: start capturing a new stroke or erasing.
 *
 * @param {PointerEvent} e
 */
function onPointerDown(e) {
  e.preventDefault();
  drawingSvg.setPointerCapture(e.pointerId);
  const pt = toSvgPt(drawingSvg, e);

  if (eraserMode) {
    eraseAt(pt.x, pt.y);
    eraserCursor = svgEl("circle", {
      cx: pt.x,
      cy: pt.y,
      r: ERASER_RADIUS,
      fill: "rgba(255,100,100,0.2)",
      stroke: "#e53e3e",
      "stroke-width": trace.unitsPerEm * 0.01,
    });
    drawingSvg.appendChild(eraserCursor);
    currentPts = [{ x: pt.x, y: pt.y }]; // reuse to track dragging
    renderGlyph();
    // Re-add cursor after re-render
    eraserCursor = svgEl("circle", {
      cx: pt.x,
      cy: pt.y,
      r: ERASER_RADIUS,
      fill: "rgba(255,100,100,0.2)",
      stroke: "#e53e3e",
      "stroke-width": trace.unitsPerEm * 0.01,
    });
    drawingSvg.appendChild(eraserCursor);
    return;
  }

  currentPts = [{ x: pt.x, y: pt.y }];

  previewPath = svgEl("path", {
    fill: "none",
    stroke: "#1a1a2e",
    "stroke-width": trace.unitsPerEm * 0.025,
    "stroke-linecap": "round",
    "stroke-linejoin": "round",
    opacity: "0.6",
  });
  drawingSvg.appendChild(previewPath);
}

/**
 * Handle pointer-move: update the live preview path or erase.
 *
 * @param {PointerEvent} e
 */
function onPointerMove(e) {
  if (!currentPts) return;
  e.preventDefault();
  const pt = toSvgPt(drawingSvg, e);

  if (eraserMode) {
    eraseAt(pt.x, pt.y);
    if (eraserCursor) {
      eraserCursor.remove();
    }
    renderGlyph();
    eraserCursor = svgEl("circle", {
      cx: pt.x,
      cy: pt.y,
      r: ERASER_RADIUS,
      fill: "rgba(255,100,100,0.2)",
      stroke: "#e53e3e",
      "stroke-width": trace.unitsPerEm * 0.01,
    });
    drawingSvg.appendChild(eraserCursor);
    return;
  }

  currentPts.push({ x: pt.x, y: pt.y });
  previewPath.setAttribute("d", smoothPath(downsample(currentPts, MIN_DIST_PREVIEW)));
}

/**
 * Handle pointer-up: commit the finished stroke or finish erasing.
 *
 * @param {PointerEvent} e
 */
function onPointerUp(e) {
  if (!currentPts) return;

  if (eraserMode) {
    currentPts = null;
    if (eraserCursor) {
      eraserCursor.remove();
      eraserCursor = null;
    }
    renderGlyph();
    return;
  }
  const pts = downsample(currentPts, MIN_DIST_RECORD);
  currentPts = null;
  previewPath = null;

  if (pts.length < 2) {
    renderGlyph();
    return;
  }

  const g = trace.glyphs[glyphIndex];
  ensureStrokes(g.clusterStr).push({ d: smoothPath(pts) });
  redoStacks[g.clusterStr] = [];
  renderGlyph();
}

// ---------------------------------------------------------------------------
// Export helpers
// ---------------------------------------------------------------------------

/**
 * Trigger a browser download of *text* as *filename*.
 *
 * @param {string} text
 * @param {string} filename
 */
function downloadText(text, filename) {
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Event wiring — runs after DOM is ready
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");

  dropZone.addEventListener("click", () => fileInput.click());
  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("over");
  });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("over"));
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("over");
    loadFile(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener("change", () => loadFile(fileInput.files[0]));

  document.getElementById("prev-btn").addEventListener("click", () => {
    const visible = visibleGlyphIndices();
    const pos = visible.indexOf(glyphIndex);
    if (pos > 0) {
      glyphIndex = visible[pos - 1];
      renderGlyph();
    }
  });
  document.getElementById("next-btn").addEventListener("click", () => {
    const visible = visibleGlyphIndices();
    const pos = visible.indexOf(glyphIndex);
    if (pos !== -1 && pos < visible.length - 1) {
      glyphIndex = visible[pos + 1];
      renderGlyph();
    }
  });
  document.getElementById("show-all-toggle").addEventListener("change", (e) => {
    showAllClusters = e.target.checked;
    populateSelect();
    renderGlyph();
  });
  document.getElementById("next-missing-btn").addEventListener("click", () => {
    const visible = visibleGlyphIndices();
    const pos = visible.indexOf(glyphIndex);
    // Search forward from just after the current position, wrapping once,
    // for the next visible cluster with no recorded stroke yet.
    const order = [...visible.slice(pos + 1), ...visible.slice(0, pos + 1)];
    const next = order.find((i) => !isRecorded(trace.glyphs[i].clusterStr));
    if (next === undefined) {
      alert("Nothing missing in the current view — every visible cluster already has a stroke.");
      return;
    }
    glyphIndex = next;
    renderGlyph();
  });
  document.getElementById("undo-btn").addEventListener("click", () => {
    const g = trace.glyphs[glyphIndex];
    const strokes = ensureStrokes(g.clusterStr);
    if (strokes.length === 0) return;
    const popped = strokes.pop();
    (redoStacks[g.clusterStr] ??= []).push(popped);
    renderGlyph();
  });
  document.getElementById("redo-btn").addEventListener("click", () => {
    const g = trace.glyphs[glyphIndex];
    const stack = redoStacks[g.clusterStr];
    if (!stack || stack.length === 0) return;
    ensureStrokes(g.clusterStr).push(stack.pop());
    renderGlyph();
  });
  document.getElementById("clear-btn").addEventListener("click", () => {
    const g = trace.glyphs[glyphIndex];
    strokeData[g.clusterStr] = [];
    redoStacks[g.clusterStr] = [];
    renderGlyph();
  });

  // ── Eraser toggle ─────────────────────────────────────────────────────
  const eraserBtn = document.getElementById("eraser-btn");
  eraserBtn.addEventListener("click", () => {
    eraserMode = !eraserMode;
    eraserBtn.classList.toggle("active", eraserMode);
    const wrap = document.getElementById("canvas-wrap");
    wrap.style.cursor = eraserMode ? "crosshair" : "crosshair";
    if (eraserMode) {
      wrap.classList.add("eraser-active");
    } else {
      wrap.classList.remove("eraser-active");
    }
  });

  document.getElementById("export-btn").addEventListener("click", () => {
    // Start from existing file data (if loaded), then overlay current session.
    const lib = existingStrokeData ? { ...existingStrokeData } : {};
    for (const [name, strokes] of Object.entries(strokeData)) {
      if (strokes.length) lib[name] = { strokes };
    }
    const out = JSON.stringify(lib, null, 2);
    document.getElementById("export-output").value = out;
    const area = document.getElementById("export-area");
    area.style.display = "block";
    area.scrollIntoView({ behavior: "smooth" });
  });

  document.getElementById("download-btn").addEventListener("click", () => {
    const text = document.getElementById("export-output").value;
    if (text) downloadText(text, "stroke-data.raw.json");
  });

  document.getElementById("copy-btn").addEventListener("click", () => {
    const text = document.getElementById("export-output").value;
    navigator.clipboard.writeText(text).then(() => {
      const btn = document.getElementById("copy-btn");
      btn.textContent = "Copied!";
      setTimeout(() => {
        btn.textContent = "Copy to clipboard";
      }, 1800);
    });
  });

  // ── Dropdown: jump to any character ───────────────────────────────────
  document.getElementById("glyph-select").addEventListener("change", (e) => {
    glyphIndex = parseInt(e.target.value, 10);
    renderGlyph();
  });

  // ── Remove: delete the current character from the session ─────────────
  document.getElementById("remove-btn").addEventListener("click", () => {
    if (!trace || trace.glyphs.length === 0) return;
    const g = trace.glyphs[glyphIndex];
    if (!confirm(`Remove "${g.clusterStr}" and all its strokes from this session?`)) return;
    delete strokeData[g.clusterStr];
    trace.glyphs.splice(glyphIndex, 1);
    if (glyphIndex >= trace.glyphs.length) glyphIndex = Math.max(0, trace.glyphs.length - 1);
    if (trace.glyphs.length === 0) {
      document.getElementById("recorder").classList.remove("active");
      document.getElementById("drop-zone").classList.remove("hidden");
      return;
    }
    populateSelect();
    renderGlyph();
  });

  // ── Add: insert a custom cluster (or jump to existing one) ────────────
  document.getElementById("add-btn").addEventListener("click", () => {
    const input = document.getElementById("add-input");
    const cluster = input.value.trim();
    if (!cluster || !trace) return;
    const existingIdx = trace.glyphs.findIndex((g) => g.clusterStr === cluster);
    if (existingIdx !== -1) {
      glyphIndex = existingIdx;
    } else {
      trace.glyphs.push({ clusterStr: cluster, paths: [], advance: trace.unitsPerEm * 0.85 });
      manuallyAddedClusters.add(cluster);
      glyphIndex = trace.glyphs.length - 1;
    }
    input.value = "";
    populateSelect();
    renderGlyph();
  });
  document.getElementById("add-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") document.getElementById("add-btn").click();
  });

  // ── Merge: load an existing stroke-data.raw.json to append to ─────────
  document.getElementById("load-existing-btn").addEventListener("click", () => {
    document.getElementById("existing-file-input").click();
  });
  document.getElementById("existing-file-input").addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        existingStrokeData = JSON.parse(ev.target.result);
        const count = Object.keys(existingStrokeData).length;
        document.getElementById("merge-status").textContent =
          `✓ ${count} existing cluster(s) loaded — export will merge`;
        // Loaded strokes redefine which multi-char clusters count as atoms
        // (see isAtom) and which show as already-recorded — refresh both.
        if (trace) {
          populateSelect();
          renderGlyph();
        }
        // Refresh textarea if it is already visible
        const out = document.getElementById("export-output").value;
        if (out) document.getElementById("export-btn").click();
      } catch (err) {
        alert("Could not load stroke-data.raw.json: " + err.message);
      }
    };
    reader.readAsText(file);
  });
});
