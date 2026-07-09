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

/**
 * Default inter-cluster tightening, as a fraction of unitsPerEm, trimmed from
 * each cluster's advance before accumulating pen position.
 *
 * The font's advance width bakes in a trailing sidebearing gap — measured at
 * a near-constant ~200/2048 em-units across this font's glyphs regardless of
 * glyph width, rather than a proportional amount — that reads as too loose
 * for this handwriting-trace UI. Trimming a fraction of it tightens
 * inter-character spacing without touching any cluster's own internal glyph
 * layout. Override per writer via `options.tighten` (see createStrokeWriter).
 */
const DEFAULT_TIGHTEN_FRACTION = 0.06;

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
 * Compose a base cluster entry with a trailing mark's prefix/suffix recipe.
 *
 * @param {{ glyphs: {d: string, x: number, y: number}[], advance: number }} base
 * @param {{ shift: number, prefix: object[], suffix: object[], trailingWidth: number }} mark
 * @returns {{ glyphs: {d: string, x: number, y: number}[], advance: number }}
 */
function composeMark(base, mark) {
  const glyphs = [
    ...mark.prefix.map((p) => ({ d: p.d, x: p.x, y: p.y })),
    ...base.glyphs.map((g) => ({ d: g.d, x: g.x + mark.shift, y: g.y })),
    ...mark.suffix.map((s) => ({ d: s.d, x: mark.shift + base.advance + s.x, y: s.y })),
  ];
  return { glyphs, advance: mark.shift + base.advance + mark.trailingWidth };
}

/**
 * Offset every absolute coordinate in an SVG path's `d` string by (dx, dy).
 * Mirrors tools/.../stroke_compose.py's `offset_svg_path` exactly — same
 * regex-based approach, needed here to compose *stroke* paths at runtime
 * the same way {@link composeMark} composes glyph outlines.
 *
 * @param {string} d
 * @param {number} dx
 * @param {number} dy
 * @returns {string}
 */
function offsetSvgPath(d, dx, dy) {
  if (dx === 0 && dy === 0) return d;
  return d.replace(/([MLCSQTHVmlcsqthv])\s*([-\d.e]+(?:\s+[-\d.e]+)*)/g, (_, cmd, coordStr) => {
    const coords = coordStr.trim().split(/\s+/).map(Number);
    const upper = cmd.toUpperCase();
    let shifted;
    if (upper === "H") shifted = coords.map((v) => v + dx);
    else if (upper === "V") shifted = coords.map((v) => v + dy);
    else shifted = coords.map((v, i) => (i % 2 === 0 ? v + dx : v + dy));
    return `${cmd} ${shifted.map((v) => v.toFixed(1)).join(" ")}`;
  });
}

/**
 * Compose a base cluster's *strokes* (not glyph outlines) with a trailing
 * mark's own recorded stroke, using the same shift/prefix/suffix recipe as
 * {@link composeMark}. This is what lets `stroke-data.json` stay small (just
 * the hand-authored + per-glyph-composed base) instead of pre-baking every
 * mark combination — the same principle already applied to `glyph-data.json`
 * via runtime composition, extended to strokes.
 *
 * Returns `null` for compound marks (both prefix and suffix parts) — only
 * one recorded stroke exists for those, and it can't be cleanly offset
 * without also warping the gap in the middle to match the base's width.
 *
 * @param {{d: string}[]} baseStrokes
 * @param {{ shift: number, prefix: object[], suffix: object[], trailingWidth: number }} mark
 * @param {{d: string}[]} markStrokes
 * @param {number} baseAdvance
 * @returns {{d: string}[] | null}
 */
function composeMarkStroke(baseStrokes, mark, markStrokes, baseAdvance) {
  if (mark.prefix.length > 0 && mark.suffix.length > 0) return null;
  const shift = mark.shift;
  const composed = baseStrokes.map((s) => ({ d: offsetSvgPath(s.d, shift, 0) }));
  if (mark.prefix.length > 0) {
    return [...markStrokes.map((s) => ({ d: s.d })), ...composed];
  }
  const dx = shift + baseAdvance;
  return [...composed, ...markStrokes.map((s) => ({ d: offsetSvgPath(s.d, dx, 0) }))];
}

/**
 * Try composing a stroke for `cluster` from a shorter base already in
 * {@link STROKE_LIBRARY} plus a trailing mark's own recorded stroke —
 * mirrors {@link resolveSegments}'s glyph-level composition, one level up.
 * Composed results are cached into `STROKE_LIBRARY` under `cluster` so
 * repeated traces of the same word don't recompose it.
 *
 * @param {string} cluster
 * @param {{ clusters: Record<string, object>, marks: Record<string, object> }} glyphData
 * @returns {{ strokes: {d: string}[] } | null}
 */
function tryComposeStroke(cluster, glyphData) {
  const { clusters, marks } = glyphData;
  for (const markLen of [2, 1]) {
    if (cluster.length <= markLen) continue;
    const baseKey = cluster.slice(0, -markLen);
    const markKey = cluster.slice(-markLen);
    const base = STROKE_LIBRARY[baseKey];
    const mark = marks?.[markKey];
    const markEntry = STROKE_LIBRARY[markKey];
    const baseGlyphEntry = clusters[baseKey];
    if (!base?.strokes?.length || !mark || !markEntry?.strokes?.length || !baseGlyphEntry) continue;
    const strokes = composeMarkStroke(base.strokes, mark, markEntry.strokes, baseGlyphEntry.advance);
    if (strokes) {
      const entry = { strokes };
      STROKE_LIBRARY[cluster] = entry;
      return entry;
    }
  }
  return null;
}

/**
 * Resolve `text` into an ordered list of `{ cluster, entry }` pairs.
 *
 * Tries a direct longest-match lookup first (4-char conjunct+matra → 3-char
 * conjunct → 2-char consonant+matra → 1-char). A character with no direct
 * match at any length — necessarily a mark, since a real base always has at
 * least a 1-char entry — is composed onto the *previously matched* segment
 * (base and mark are adjacent by construction, so "the segment just pushed"
 * is exactly the base this mark attaches to) — see {@link composeMark}. Mark
 * lookup tries a 2-char tail first (subjoined conjunct forms — virama plus a
 * reduced ya/va/la, e.g. "്യ") before falling back to 1-char (virama or a
 * dependent vowel sign alone), same longest-match precedence as direct
 * cluster lookups. Some marks (ു/ൂ/ൃ, and subjoined la) fuse into a glyph
 * unique to the specific preceding consonant in real shaping — composing
 * them generically can't reproduce that exact fused glyph, so they render
 * as the base's own glyph plus the mark's separate standalone shape
 * instead: less tightly kerned than a true font ligature, but still correct
 * and legible (see glyphData.marks / tools/build_glyph_data.py's
 * _build_marks() docstring for the full derivation). Composition is skipped
 * only for marks with a prefix component when the base is more than one
 * glyph — that reordering isn't safe on a non-ligating multi-glyph
 * conjunct. A mark with nothing to attach to (no previous segment, or that
 * unsupported prefix+multi-glyph case) is skipped with a console warning.
 *
 * @param {string} text
 * @param {Record<string, unknown>} clusters - The `clusters` map from glyph-data.json.
 * @param {Record<string, unknown>} marks - The `marks` map from glyph-data.json.
 * @returns {{ cluster: string, entry: { glyphs: object[], advance: number } }[]}
 */
function resolveSegments(text, clusters, marks) {
  const segs = [];
  let i = 0;
  while (i < text.length) {
    let matched = false;
    for (const len of [4, 3, 2, 1]) {
      if (i + len > text.length) continue;
      const slice = text.slice(i, i + len);
      if (clusters[slice]) {
        segs.push({ cluster: slice, entry: clusters[slice] });
        i += len;
        matched = true;
        break;
      }
    }
    if (matched) continue;

    let composed = false;
    for (const markLen of [2, 1]) {
      if (i + markLen > text.length) continue;
      const markCh = text.slice(i, i + markLen);
      const mark = marks[markCh];
      const prev = segs[segs.length - 1];
      if (!mark || !prev) continue;
      if (mark.prefix.length > 0 && prev.entry.glyphs.length > 1) continue;
      segs[segs.length - 1] = {
        cluster: prev.cluster + markCh,
        entry: composeMark(prev.entry, mark),
      };
      i += markLen;
      composed = true;
      break;
    }
    if (composed) continue;

    console.warn(`malayalam-stroker: no glyph data for ${JSON.stringify(text[i])} in ${JSON.stringify(text)} — skipping`);
    i++;
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
 * @param {{ speed?: number, glyphData?: object, tighten?: number }} [options]
 * @param {number} [options.speed=6000] - Nominal pen speed in font-units per second.
 * @param {object} [options.glyphData=null] - Pre-loaded glyph data object (skips `load()`).
 * @param {number} [options.tighten=0.06] - Inter-cluster tightening, as a fraction of
 *   unitsPerEm trimmed from each cluster's advance. 0 reproduces the font's raw spacing;
 *   higher values pull characters closer together. See {@link DEFAULT_TIGHTEN_FRACTION}.
 * @param {boolean} [options.outlineOnly=false] - Ignore {@link STROKE_LIBRARY} entirely and
 *   always animate the outer-contour outline fallback, even for clusters with authored
 *   strokes. Useful for a consistent tracing style independent of authoring coverage
 *   (e.g. a wordmark mixing authored and not-yet-authored clusters).
 * @returns {{ load: Function, loadStrokes: Function, play: Function, replay: Function, cancel: Function, destroy: Function }}
 */
export function createStrokeWriter(container, options = {}) {
  const SPEED = options.speed ?? 6000;
  const TIGHTEN = options.tighten ?? DEFAULT_TIGHTEN_FRACTION;
  const OUTLINE_ONLY = options.outlineOnly ?? false;
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
    const { meta, clusters, marks } = glyphData;
    const segs = resolveSegments(text, clusters, marks ?? {});
    if (!segs.length) return null;

    const tightenUnits = TIGHTEN * meta.unitsPerEm;
    let penX = 0;
    const segGroups = [];
    for (const { cluster, entry } of segs) {
      segGroups.push({
        cluster,
        components: entry.glyphs.map((g) => ({ d: g.d, x: penX + g.x, y: g.y })),
        groupX: penX,
      });
      penX += Math.max(0, entry.advance - tightenUnits);
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
      const authored = OUTLINE_ONLY
        ? null
        : (STROKE_LIBRARY[grp.cluster] ?? tryComposeStroke(grp.cluster, glyphData));

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
          // Normally only the outer contour is traced (inner counters/holes
          // are skipped as separate pen-strokes). outlineOnly requests the
          // full accurate outline instead, so trace every subpath.
          if (!OUTLINE_ONLY && !isOuter[i]) return [];
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
