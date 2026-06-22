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

  // Previously recorded strokes with numbered start-point badges
  const strokes = strokeData[g.clusterStr] ?? [];
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

  document.getElementById("glyph-label").innerHTML =
    `<strong>${g.clusterStr}</strong> &nbsp;·&nbsp; ${glyphIndex + 1} / ${trace.glyphs.length}`;

  updateCounts();

  document.getElementById("prev-btn").disabled = glyphIndex === 0;
  document.getElementById("next-btn").disabled = glyphIndex === trace.glyphs.length - 1;

  svg.addEventListener("pointerdown", onPointerDown);
  svg.addEventListener("pointermove", onPointerMove);
  svg.addEventListener("pointerup", onPointerUp);
  svg.addEventListener("pointercancel", onPointerUp);
}

/**
 * Refresh the stroke counter and undo-button state.
 */
function updateCounts() {
  const g = trace.glyphs[glyphIndex];
  const n = (strokeData[g.clusterStr] ?? []).length;
  document.getElementById("stroke-count").textContent =
    `${n} stroke${n !== 1 ? "s" : ""} recorded`;
  document.getElementById("undo-btn").disabled = n === 0;
}

// ---------------------------------------------------------------------------
// Drawing event handlers
// ---------------------------------------------------------------------------

/**
 * Handle pointer-down: start capturing a new stroke.
 *
 * @param {PointerEvent} e
 */
function onPointerDown(e) {
  e.preventDefault();
  drawingSvg.setPointerCapture(e.pointerId);
  const pt = toSvgPt(drawingSvg, e);
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
 * Handle pointer-move: update the live preview path.
 *
 * @param {PointerEvent} e
 */
function onPointerMove(e) {
  if (!currentPts) return;
  e.preventDefault();
  const pt = toSvgPt(drawingSvg, e);
  currentPts.push({ x: pt.x, y: pt.y });
  previewPath.setAttribute("d", smoothPath(downsample(currentPts, MIN_DIST_PREVIEW)));
}

/**
 * Handle pointer-up: commit the finished stroke.
 *
 * @param {PointerEvent} e
 */
function onPointerUp(e) {
  if (!currentPts) return;
  const pts = downsample(currentPts, MIN_DIST_RECORD);
  currentPts = null;
  previewPath = null;

  if (pts.length < 2) {
    renderGlyph();
    return;
  }

  const g = trace.glyphs[glyphIndex];
  if (!strokeData[g.clusterStr]) strokeData[g.clusterStr] = [];
  strokeData[g.clusterStr].push({ d: smoothPath(pts) });
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
    if (glyphIndex > 0) {
      glyphIndex--;
      renderGlyph();
    }
  });
  document.getElementById("next-btn").addEventListener("click", () => {
    if (glyphIndex < (trace?.glyphs.length ?? 0) - 1) {
      glyphIndex++;
      renderGlyph();
    }
  });
  document.getElementById("undo-btn").addEventListener("click", () => {
    const g = trace.glyphs[glyphIndex];
    strokeData[g.clusterStr]?.pop();
    renderGlyph();
  });
  document.getElementById("clear-btn").addEventListener("click", () => {
    const g = trace.glyphs[glyphIndex];
    strokeData[g.clusterStr] = [];
    renderGlyph();
  });

  document.getElementById("export-btn").addEventListener("click", () => {
    const lib = {};
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
    if (text) downloadText(text, "stroke-data.json");
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
});
