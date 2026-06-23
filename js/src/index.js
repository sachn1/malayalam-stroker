/**
 * malayalam-stroker — self-contained stroke-trace animation library.
 *
 * No server, no font file, no build step required at runtime.
 *
 * Two data files, both committed to the repo:
 *   glyph-data.json  — font-specific SVG outlines + advance widths.
 *                      Re-generate when the font changes:
 *                        python tools/build_glyph_data.py [/path/to/Font.ttf]
 *   stroke-data.json — font-agnostic hand-authored centerline strokes,
 *                      produced by tools/stroke-recorder.html.
 *                      Falls back to outer-contour outline when absent.
 *
 * @example
 * import { createStrokeWriter } from "malayalam-stroker";
 * const writer = createStrokeWriter(document.getElementById("stage"));
 * await writer.load();
 * await writer.loadStrokes();   // optional — silent no-op if file absent
 * await writer.play("നന്ദി");
 *
 * @module malayalam-stroker
 */

const SVGNS = "http://www.w3.org/2000/svg";

/** Number of sample points used when resampling an outline subpath. */
const OUTLINE_SAMPLES = 200;

/** Pause between consecutive strokes of one glyph (milliseconds). */
const PEN_LIFT_MS = 120;

/** Default URL for the bundled glyph data. */
const GLYPH_DATA_URL = new URL("./glyph-data.json", import.meta.url);

/** Default URL for the bundled stroke data. */
const STROKE_DATA_URL = new URL("./stroke-data.json", import.meta.url);

/**
 * Per-cluster start-point overrides.
 * Key: Unicode cluster string. Value: "leftmost" | "rightmost" | "topmost" |
 * "bottommost" | number (0–1, fraction of path length), or an array of those
 * for multi-stroke glyphs.
 *
 * @type {Record<string, string | number | Array<string | number>>}
 */
export const START_OVERRIDES = {};

/**
 * Per-cluster direction overrides.
 * Key: Unicode cluster string. Value: "forward" | "reverse", or an array.
 *
 * @type {Record<string, string | Array<string>>}
 */
export const DIRECTION_OVERRIDES = {};

/**
 * Hand-authored centerline strokes, keyed by Unicode cluster.
 * Populated at runtime by {@link loadStrokes}.
 * Keys: Unicode cluster strings ("ന", "ക്ഷ").
 * Values: `{ strokes: [{ d: "M ..." }] }`.
 *
 * @type {Record<string, { strokes: { d: string }[] }>}
 */
export const STROKE_LIBRARY = {};

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Create an SVG element with the given attributes.
 *
 * @param {string} tag
 * @param {Record<string, string | number>} attrs
 * @returns {SVGElement}
 */
function svgEl(tag, attrs) {
  const el = document.createElementNS(SVGNS, tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  return el;
}

/**
 * Split a compound SVG `d` string into individual subpath strings.
 *
 * @param {string} d
 * @returns {string[]}
 */
function splitSubpaths(d) {
  return d.match(/M[^M]*/g) ?? [d];
}

/**
 * Resolve the start-point override for a cluster and stroke index.
 *
 * @param {string} cluster
 * @param {number} i
 * @returns {string | number}
 */
function resolveStart(cluster, i) {
  const e = START_OVERRIDES[cluster];
  if (e === undefined) return "leftmost";
  return Array.isArray(e) ? (e[i] ?? "leftmost") : e;
}

/**
 * Resolve the direction override for a cluster and stroke index.
 *
 * @param {string} cluster
 * @param {number} i
 * @returns {string}
 */
function resolveDirection(cluster, i) {
  const e = DIRECTION_OVERRIDES[cluster];
  if (e === undefined) return "forward";
  return Array.isArray(e) ? (e[i] ?? "forward") : e;
}

/**
 * Classify subpaths of a glyph outline as outer (true) or inner hole (false).
 *
 * A subpath whose arc length is at least 45% of the longest subpath is
 * considered an outer contour; shorter ones are treated as interior holes.
 *
 * @param {string[]} subDs - Individual subpath `d` strings.
 * @param {SVGPathElement} scratch - Reusable off-screen path element.
 * @returns {boolean[]}
 */
function classifySubpaths(subDs, scratch) {
  const lengths = subDs.map((d) => {
    scratch.setAttribute("d", d);
    return scratch.getTotalLength();
  });
  const max = Math.max(...lengths);
  return lengths.map((l) => l >= max * 0.45);
}

/**
 * Resample an SVG outline path and return a smooth animated trace path string.
 *
 * The trace starts at the point specified by `startOverride`, then follows the
 * path in `direction` order. The result can be fed directly to a
 * `stroke-dasharray` / `stroke-dashoffset` animation.
 *
 * @param {SVGPathElement} pathEl - Path element with the outline `d` set.
 * @param {string | number} startOverride - "leftmost" | "rightmost" | "topmost" | "bottommost" | fraction.
 * @param {string} direction - "forward" | "reverse".
 * @returns {string} SVG path `d` string, or `""` if the path has no length.
 */
function buildTracePath(pathEl, startOverride, direction) {
  const len = pathEl.getTotalLength();
  if (len <= 0) return "";

  let pts = Array.from({ length: OUTLINE_SAMPLES }, (_, i) =>
    pathEl.getPointAtLength((i / OUTLINE_SAMPLES) * len)
  );

  let si = 0;
  if (typeof startOverride === "number") {
    si = Math.round(startOverride * OUTLINE_SAMPLES) % OUTLINE_SAMPLES;
  } else {
    const axis = { leftmost: "x", rightmost: "x", topmost: "y", bottommost: "y" }[startOverride] ?? "x";
    const prefer =
      startOverride === "rightmost" || startOverride === "bottommost"
        ? (a, b) => a > b
        : (a, b) => a < b;
    let best = pts[0][axis];
    for (let i = 1; i < pts.length; i++) {
      if (prefer(pts[i][axis], best)) {
        best = pts[i][axis];
        si = i;
      }
    }
  }

  pts = [...pts.slice(si), ...pts.slice(0, si)];
  if (direction === "reverse") pts = [pts[0], ...pts.slice(1).reverse()];

  return "M " + pts.map((p) => `${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" L ") + " Z";
}

// ---------------------------------------------------------------------------
// Segmentation
// ---------------------------------------------------------------------------

/**
 * Segment `text` into Unicode clusters using longest-match lookup.
 *
 * Tries 3-char conjunct → 2-char consonant+matra → 1-char. Unknown
 * codepoints are silently skipped.
 *
 * @param {string} text
 * @param {Record<string, unknown>} clusters - The `clusters` map from glyph-data.json.
 * @returns {string[]} Ordered list of matched cluster strings.
 */
function segmentText(text, clusters) {
  const segs = [];
  let i = 0;
  while (i < text.length) {
    if (i + 2 < text.length && clusters[text.slice(i, i + 3)]) {
      segs.push(text.slice(i, i + 3));
      i += 3;
    } else if (i + 1 < text.length && clusters[text.slice(i, i + 2)]) {
      segs.push(text.slice(i, i + 2));
      i += 2;
    } else if (clusters[text[i]]) {
      segs.push(text[i]);
      i++;
    } else {
      i++;
    }
  }
  return segs;
}

// ---------------------------------------------------------------------------
// Public factory
// ---------------------------------------------------------------------------

/**
 * Create a stroke-writer bound to `container`.
 *
 * @param {HTMLElement} container - The DOM element that will hold the SVG stage.
 * @param {{ speed?: number, glyphData?: object }} [options]
 * @param {number} [options.speed=6000] - Nominal pen speed in font-units per second.
 * @param {object} [options.glyphData=null] - Pre-loaded glyph data object (skips `load()`).
 * @returns {{ load: Function, loadStrokes: Function, play: Function, replay: Function, cancel: Function, destroy: Function }}
 */
export function createStrokeWriter(container, options = {}) {
  const SPEED = options.speed ?? 6000;
  const state = { playToken: 0 };
  let glyphData = options.glyphData ?? null;
  let lastText = null;

  // ── Data loading ──────────────────────────────────────────────────────

  /**
   * Fetch and cache glyph-data.json (idempotent).
   *
   * @param {string | URL} [url] - Defaults to the bundled glyph-data.json.
   * @returns {Promise<void>}
   */
  async function load(url = GLYPH_DATA_URL) {
    if (glyphData) return;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`Failed to load glyph data: ${resp.status}`);
    glyphData = await resp.json();
  }

  /**
   * Fetch stroke-data.json and merge into {@link STROKE_LIBRARY} (idempotent).
   *
   * A missing file (404 or network error) is silently ignored — the library
   * simply falls back to outline-based animation for unrecognised clusters.
   * Existing keys are never overwritten so multiple calls are safe.
   *
   * @param {string | URL} [url] - Defaults to the bundled stroke-data.json.
   * @returns {Promise<void>}
   */
  async function loadStrokes(url = STROKE_DATA_URL) {
    let resp;
    try {
      resp = await fetch(url);
    } catch {
      return;
    }
    if (!resp.ok) return;
    const data = await resp.json();
    for (const [cluster, entry] of Object.entries(data)) {
      if (!STROKE_LIBRARY[cluster]) STROKE_LIBRARY[cluster] = entry;
    }
  }

  // ── Trace building ────────────────────────────────────────────────────

  /**
   * Segment `text` and build the per-cluster group list.
   *
   * Each group corresponds to one Unicode cluster. Components are the
   * individual HarfBuzz glyphs that make up the cluster and are used for
   * ghost rendering and outline fallback — authored strokes fire once per
   * group, not once per component.
   *
   * @param {string} text
   * @returns {{ unitsPerEm: number, ascent: number, descent: number, totalAdvance: number, segGroups: object[] } | null}
   */
  function buildTrace(text) {
    if (!glyphData) throw new Error("Call writer.load() before writer.play()");
    const { meta, clusters } = glyphData;
    const segs = segmentText(text, clusters);
    if (!segs.length) return null;

    let penX = 0;
    const segGroups = [];
    for (const seg of segs) {
      const entry = clusters[seg];
      if (!entry) continue;
      segGroups.push({
        cluster: seg,
        components: entry.glyphs.map((g) => ({ d: g.d, x: penX + g.x, y: g.y })),
        groupX: penX,
      });
      penX += entry.advance;
    }

    return {
      unitsPerEm: meta.unitsPerEm,
      ascent: meta.ascent,
      descent: meta.descent,
      totalAdvance: penX,
      segGroups,
    };
  }

  // ── Stage building ────────────────────────────────────────────────────

  /**
   * Render the ghost letterforms and animated stroke paths into `container`.
   *
   * @param {{ unitsPerEm: number, ascent: number, descent: number, totalAdvance: number, segGroups: object[] }} trace
   * @returns {{ glyphUnits: object[], stylus: SVGCircleElement }}
   */
  function buildStage(trace) {
    container.innerHTML = "";
    const { unitsPerEm, ascent, descent, totalAdvance, segGroups } = trace;
    const pad = unitsPerEm * 0.1;
    const vb = `${-pad} ${-ascent - pad} ${totalAdvance + pad * 2} ${ascent - descent + pad * 2}`;
    const svg = svgEl("svg", { viewBox: vb });

    // Ghost: filled outlines of all clusters.
    const ghostG = svgEl("g", { class: "ms-ghost" });
    for (const grp of segGroups) {
      for (const c of grp.components) {
        ghostG.appendChild(svgEl("path", { d: c.d, transform: `translate(${c.x},${c.y})` }));
      }
    }
    svg.appendChild(ghostG);
    container.appendChild(svg);

    // Off-screen scratch path for arc-length measurement.
    const defs = svgEl("defs", {});
    const scratch = svgEl("path", { fill: "none", stroke: "none" });
    defs.appendChild(scratch);
    svg.appendChild(defs);

    const sw = unitsPerEm * 0.022;
    const stylus = svgEl("circle", { class: "ms-stylus", r: unitsPerEm * 0.016 });
    stylus.style.opacity = "0";
    svg.appendChild(stylus);

    const glyphUnits = segGroups.map((grp) => {
      const authored = STROKE_LIBRARY[grp.cluster];

      // Authored path: one group element translated to the cluster origin.
      if (authored?.strokes?.length) {
        const gEl = svgEl("g", { transform: `translate(${grp.groupX},0)` });
        svg.appendChild(gEl);
        const tr = { x: grp.groupX, y: 0 };
        const subUnits = authored.strokes.map((s) => {
          const el = svgEl("path", {
            d: s.d,
            class: "ms-stroke",
            "stroke-width": sw,
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
          });
          gEl.appendChild(el);
          const len = el.getTotalLength();
          if (len > 0) {
            el.setAttribute("stroke-dasharray", `${len} ${len}`);
            el.setAttribute("stroke-dashoffset", String(len));
          }
          return { strokeEl: el, len, tr };
        });
        return { gEl, subUnits };
      }

      // Outline fallback: resample the outer contour of each component.
      let strokeIndex = 0;
      const subUnits = grp.components.flatMap((c) => {
        const subDs = splitSubpaths(c.d);
        const isOuter = classifySubpaths(subDs, scratch);
        return subDs.flatMap((subD, i) => {
          if (!isOuter[i]) return [];
          scratch.setAttribute("d", subD);
          const td = buildTracePath(
            scratch,
            resolveStart(grp.cluster, strokeIndex),
            resolveDirection(grp.cluster, strokeIndex)
          );
          strokeIndex++;
          if (!td) return [];
          const cEl = svgEl("g", { transform: `translate(${c.x},${c.y})` });
          svg.appendChild(cEl);
          const el = svgEl("path", {
            d: td,
            class: "ms-stroke",
            "stroke-width": sw,
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
          });
          cEl.appendChild(el);
          const len = el.getTotalLength();
          if (len > 0) {
            el.setAttribute("stroke-dasharray", `${len} ${len}`);
            el.setAttribute("stroke-dashoffset", String(len));
          }
          return [{ strokeEl: el, len, tr: { x: c.x, y: c.y } }];
        });
      });
      return { gEl: null, subUnits };
    });

    return { glyphUnits, stylus };
  }

  // ── Animation ─────────────────────────────────────────────────────────

  /**
   * Animate one stroke sub-unit using the dash-offset technique.
   *
   * @param {{ strokeEl: SVGPathElement, len: number, tr: { x: number, y: number }, dMs: number }} unit
   * @param {SVGCircleElement} stylus
   * @param {number} token - Cancellation token; animation aborts if it changes.
   * @returns {Promise<void>}
   */
  function traceSub(unit, stylus, token) {
    return new Promise((resolve) => {
      const { strokeEl, len, tr, dMs } = unit;
      if (len <= 0) return resolve();

      const p0 = strokeEl.getPointAtLength(0);
      stylus.setAttribute("cx", String(p0.x + tr.x));
      stylus.setAttribute("cy", String(p0.y + tr.y));
      stylus.style.opacity = "1";

      const t0 = performance.now();
      function frame(now) {
        if (token !== state.playToken) return resolve();
        const t = Math.max(0, Math.min(1, (now - t0) / dMs));
        strokeEl.setAttribute("stroke-dashoffset", String(len * (1 - t)));
        const pt = strokeEl.getPointAtLength(t * len);
        stylus.setAttribute("cx", String(pt.x + tr.x));
        stylus.setAttribute("cy", String(pt.y + tr.y));
        if (t < 1) requestAnimationFrame(frame);
        else resolve();
      }
      requestAnimationFrame(frame);
    });
  }

  /**
   * Animate all sub-units of one glyph group in sequence.
   *
   * @param {{ subUnits: object[] }} unit
   * @param {SVGCircleElement} stylus
   * @param {number} dMs - Total duration for this glyph in milliseconds.
   * @param {number} token
   * @returns {Promise<void>}
   */
  async function traceGlyph(unit, stylus, dMs, token) {
    const totalLen = unit.subUnits.reduce((s, u) => s + u.len, 0) || 1;
    for (const sub of unit.subUnits) {
      sub.dMs = Math.max(80, dMs * (sub.len / totalLen));
    }
    for (const [i, sub] of unit.subUnits.entries()) {
      if (token !== state.playToken) return;
      await traceSub(sub, stylus, token);
      if (i < unit.subUnits.length - 1) {
        stylus.style.opacity = "0";
        await new Promise((r) => setTimeout(r, PEN_LIFT_MS));
      }
    }
    stylus.style.opacity = "0";
  }

  // ── Public API ────────────────────────────────────────────────────────

  /**
   * Animate `text` from scratch.
   *
   * Calls `load()` automatically if glyph data has not been loaded yet.
   *
   * @param {string} text - Malayalam (or any supported script) text.
   * @param {{ speed?: number }} [playOptions]
   * @param {number} [playOptions.speed=1] - Speed multiplier (>1 = faster).
   * @returns {Promise<void>}
   */
  async function play(text, playOptions = {}) {
    if (!glyphData) await load();
    lastText = text;
    const trace = buildTrace(text);
    if (!trace) return;

    const speedMul = playOptions.speed ?? 1;
    const token = ++state.playToken;
    const { glyphUnits, stylus } = buildStage(trace);

    for (const unit of glyphUnits) {
      if (token !== state.playToken) return;
      const totalLen = unit.subUnits.reduce((s, u) => s + u.len, 0) || 1;
      await traceGlyph(
        unit,
        stylus,
        Math.max(200, (totalLen / (SPEED * speedMul)) * 1000),
        token
      );
    }
    if (token === state.playToken) stylus.style.opacity = "0";
  }

  /**
   * Replay the last traced text.
   *
   * @param {{ speed?: number }} [options]
   * @returns {Promise<void>}
   */
  function replay(options = {}) {
    return lastText ? play(lastText, options) : Promise.resolve();
  }

  /** Cancel any in-progress animation immediately. */
  function cancel() {
    state.playToken++;
  }

  /** Cancel animation and remove all DOM nodes from `container`. */
  function destroy() {
    cancel();
    container.innerHTML = "";
    lastText = null;
  }

  return { load, loadStrokes, play, replay, cancel, destroy };
}
