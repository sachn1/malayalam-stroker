/**
 * malayalam-stroker - self-contained stroke-trace animation library.
 *
 * No server, no font file, no build step required at runtime.
 *
 * Two data files, both committed to the repo:
 *   glyph-data.json  - font-specific SVG outlines + advance widths.
 *                      Re-generate when the font changes:
 *                        python tools/build_glyph_data.py [/path/to/Font.ttf]
 *   stroke-data.json - font-agnostic hand-authored centerline strokes,
 *                      produced by tools/stroke-recorder.html.
 *                      Falls back to outer-contour outline when absent.
 *
 * @example
 * import { createStrokeWriter } from "malayalam-stroker";
 * const writer = createStrokeWriter(document.getElementById("stage"));
 * await writer.load();
 * await writer.loadStrokes();   // optional - silent no-op if file absent
 * await writer.play("നന്ദി");
 *
 * @module malayalam-stroker
 */

const SVGNS = "http://www.w3.org/2000/svg";

/** Number of sample points used when resampling an outline subpath. */
const OUTLINE_SAMPLES = 200;

/** Pause between consecutive strokes of one glyph (milliseconds). */
const PEN_LIFT_MS = 120;

/** Pause between repeats when `play`/`replay` is given `count > 1` (milliseconds). */
const REPLAY_PAUSE_MS = 500;

/**
 * Default inter-cluster tightening, as a fraction of unitsPerEm, trimmed from
 * each cluster's advance before accumulating pen position.
 *
 * The font's advance width bakes in a trailing sidebearing gap - measured at
 * a near-constant ~200/2048 em-units across this font's glyphs regardless of
 * glyph width, rather than a proportional amount - that reads as too loose
 * for this handwriting-trace UI. Trimming a fraction of it tightens
 * inter-character spacing without touching any cluster's own internal glyph
 * layout. Override per writer via `options.tighten` (see createStrokeWriter).
 */
const DEFAULT_TIGHTEN_FRACTION = 0.06;

/**
 * Default ink line thickness, as a fraction of unitsPerEm. Override per
 * writer via `options.strokeWidth` (see createStrokeWriter).
 */
const DEFAULT_STROKE_WIDTH_FRACTION = 0.022;

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
 * Resolve `cluster`'s ghost glyph entry ({glyphs, advance}), composing it
 * from a shorter base + mark recursively when it isn't already a directly
 * registered `clusters` entry - mirrors {@link resolveSegments}'s top-level
 * ghost composition, but keyed for lookup by any (possibly-composed) cluster
 * string rather than built up while parsing text left-to-right.
 *
 * {@link tryComposeStroke} needs this: it requires each intermediate base's
 * *advance* to position a composed mark stroke, even when that intermediate
 * cluster (e.g. "ത്സ്യ" en route to "ത്സ്യം") was never itself pre-baked as
 * its own glyph-data entry - only its own base ("ത്സ") and the mark ("്യ")
 * were. Without this, tryComposeStroke bails on any 2+-level mark chain
 * whose intermediate step isn't separately registered, silently dropping to
 * the outline-trace fallback even when every stroke it needs is available.
 *
 * @param {string} cluster
 * @param {Record<string, object>} clusters
 * @param {Record<string, object>} marks
 * @returns {{ glyphs: object[], advance: number } | null}
 */
function resolveGhostEntry(cluster, clusters, marks) {
  if (clusters[cluster]) return clusters[cluster];
  for (const markLen of [2, 1]) {
    if (cluster.length <= markLen) continue;
    const baseKey = cluster.slice(0, -markLen);
    const markKey = cluster.slice(-markLen);
    const mark = marks[markKey];
    if (!mark) continue;
    const base = resolveGhostEntry(baseKey, clusters, marks);
    if (!base) continue;
    return composeMark(base, mark);
  }
  return null;
}

/**
 * Offset every absolute coordinate in an SVG path's `d` string by (dx, dy).
 * Mirrors tools/.../stroke_compose.py's `offset_svg_path` exactly - same
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
 * Compound vowel signs decomposed into the simpler marks they're built from,
 * in application order (each applied to the *result* of the previous one).
 * ൊ/ോ/ൌ match their official Unicode canonical decomposition (NFD: ൊ→െ+ാ,
 * ോ→േ+ാ, ൌ→െ+ൗ); ൈ has no such decomposition and, in this font, shapes as a
 * single prefix-only glyph rather than two, so it's deliberately left out -
 * it composes fine as its own atom already (see {@link tryComposeStroke}).
 *
 * @type {Record<string, string[]>}
 */
const SPLIT_VOWEL_PARTS = {
  "ൊ": ["െ", "ാ"],
  "ോ": ["േ", "ാ"],
  "ൌ": ["െ", "ൗ"],
};

/**
 * The x-position where a mark's own *content* glyph (as opposed to the
 * dotted-circle placeholder HarfBuzz inserts for a base-less combining
 * mark) naturally sits in that mark's standalone `clusters` entry.
 *
 * A suffix mark's standalone shaping is [circle, content] - HarfBuzz's own
 * cluster order - so content is the *last* glyph, typically offset well
 * past 0 (the circle's own advance width). A prefix mark's standalone
 * shaping reorders to [content, circle] (prefix marks visually precede
 * their base, circle or not), so content is already the *first* glyph, at
 * x=0 - no correction needed there, which is why this is only read for the
 * suffix case in {@link applyMarkStroke}.
 *
 * A hand-drawn stroke for that mark was traced over this same standalone
 * ghost, so it's anchored at this x, not 0 - unlike the marks-table's own
 * `suffix` glyph array, which `_build_marks()` (tools/build_glyph_data.py)
 * already re-anchors to 0. Returns 0 (no correction) for marks with no
 * standalone `clusters` entry at all (the 2-char subjoined forms
 * ്യ/്വ/്ല, never added there - see `_standalone_inputs()`).
 *
 * @param {string} markKey
 * @param {Record<string, object>} clusters
 * @returns {number}
 */
function markContentAnchorX(markKey, clusters) {
  const entry = clusters?.[markKey];
  if (!entry || entry.glyphs.length < 2) return 0;
  return entry.glyphs[entry.glyphs.length - 1].x;
}

/**
 * Compose a base cluster's *strokes* (not glyph outlines) with a trailing
 * mark's own recorded stroke, using the same shift/prefix/suffix recipe as
 * {@link composeMark}. This is what lets `stroke-data.json` stay small (just
 * the hand-authored + per-glyph-composed base) instead of pre-baking every
 * mark combination - the same principle already applied to `glyph-data.json`
 * via runtime composition, extended to strokes.
 *
 * Returns `null` for compound marks (both prefix and suffix parts) - only
 * one recorded stroke exists for those, and it can't be cleanly offset
 * without also warping the gap in the middle to match the base's width.
 * {@link tryComposeStroke} handles that case instead, by applying the
 * mark's {@link SPLIT_VOWEL_PARTS} one at a time through this function.
 *
 * @param {{d: string}[]} baseStrokes
 * @param {{ shift: number, prefix: object[], suffix: object[], trailingWidth: number }} mark
 * @param {{d: string}[]} markStrokes
 * @param {number} baseAdvance
 * @param {number} [markAnchorX] - See {@link markContentAnchorX}; only used for suffix marks.
 * @returns {{ strokes: {d: string}[], advance: number } | null}
 */
function applyMarkStroke(baseStrokes, mark, markStrokes, baseAdvance, markAnchorX = 0) {
  if (mark.prefix.length > 0 && mark.suffix.length > 0) return null;
  const shift = mark.shift;
  const composed = baseStrokes.map((s) => ({ d: offsetSvgPath(s.d, shift, 0) }));
  const strokes =
    mark.prefix.length > 0
      ? [...markStrokes.map((s) => ({ d: s.d })), ...composed]
      : [
          ...composed,
          ...markStrokes.map((s) => ({ d: offsetSvgPath(s.d, shift + baseAdvance - markAnchorX, 0) })),
        ];
  return { strokes, advance: shift + baseAdvance + mark.trailingWidth };
}

/**
 * Apply a sequence of single-sided marks (each looked up and offset via
 * {@link applyMarkStroke}) to a base, one after another - used to compose a
 * compound vowel sign from its {@link SPLIT_VOWEL_PARTS} instead of needing
 * its own recorded stroke. Requires every part to already have a recorded
 * stroke in {@link STROKE_LIBRARY} (e.g. "െ" and "ാ" for ൊ); returns `null`
 * if any part is missing or its recipe is itself unexpectedly compound.
 *
 * @param {{d: string}[]} strokes
 * @param {number} advance
 * @param {string[]} markChars
 * @param {Record<string, object>} marks
 * @param {Record<string, object>} clusters
 * @returns {{ strokes: {d: string}[], advance: number } | null}
 */
function applySequentialMarkStrokes(strokes, advance, markChars, marks, clusters) {
  let result = { strokes, advance };
  for (const mc of markChars) {
    const mark = marks?.[mc];
    const markEntry = STROKE_LIBRARY[mc];
    if (!mark || !markEntry?.strokes?.length) return null;
    result = applyMarkStroke(result.strokes, mark, markEntry.strokes, result.advance, markContentAnchorX(mc, clusters));
    if (!result) return null;
  }
  return result;
}

/**
 * Compose `markKey` directly onto `base` via its own recorded stroke and
 * marks-table recipe (the common case: a single-sided mark like ാ/ി/ീ/്).
 *
 * @param {{d: string}[]} baseStrokes
 * @param {number} baseAdvance
 * @param {string} markKey
 * @param {Record<string, object>} marks
 * @param {Record<string, object>} clusters
 * @returns {{ strokes: {d: string}[], advance: number } | null}
 */
function tryDirectMarkStroke(baseStrokes, baseAdvance, markKey, marks, clusters) {
  const mark = marks?.[markKey];
  const markEntry = STROKE_LIBRARY[markKey];
  if (!mark || !markEntry?.strokes?.length) return null;
  return applyMarkStroke(baseStrokes, mark, markEntry.strokes, baseAdvance, markContentAnchorX(markKey, clusters));
}

/**
 * Try composing a stroke for `cluster` from a shorter base plus a trailing
 * mark - mirrors {@link resolveSegments}'s glyph-level composition, one
 * level up. The base isn't required to already be in {@link STROKE_LIBRARY}
 * - if it's itself a multi-character cluster with no stroke yet (e.g.
 * "ദ്യ" while composing "ദ്യു"), it's composed recursively first, so a
 * chain of marks (conjunct + subjoined form + vowel sign) resolves down to
 * its recorded atoms instead of bailing at the first not-yet-cached link.
 * Recursion always strips at least one character per call, so it bottoms
 * out within `cluster.length` levels.
 *
 * A compound 1-char mark (both prefix and suffix, e.g. ൊ/ോ/ൌ) is composed
 * via its {@link SPLIT_VOWEL_PARTS} instead of its own stroke - see {@link
 * applySequentialMarkStrokes}. Composed results are cached into {@link
 * STROKE_LIBRARY} under `cluster` so repeated traces of the same word (or
 * repeated use of the same intermediate base) don't recompose it.
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
    const base = STROKE_LIBRARY[baseKey] ?? tryComposeStroke(baseKey, glyphData);
    const baseGlyphEntry = resolveGhostEntry(baseKey, clusters, marks);
    if (!base?.strokes?.length || !baseGlyphEntry) continue;

    const splitParts = markLen === 1 ? SPLIT_VOWEL_PARTS[markKey] : undefined;
    const result = splitParts
      ? applySequentialMarkStrokes(base.strokes, baseGlyphEntry.advance, splitParts, marks, clusters)
      : tryDirectMarkStroke(base.strokes, baseGlyphEntry.advance, markKey, marks, clusters);

    if (result) {
      const entry = { strokes: result.strokes };
      STROKE_LIBRARY[cluster] = entry;
      return entry;
    }
  }
  return null;
}

/**
 * How far to shift character `ch`'s own recorded stroke so it lands at
 * `targetGx` within a larger cluster - mirrors
 * tools/.../stroke_compose.py's `_char_dx` exactly (same anchor
 * correction for a multi-glyph standalone entry, e.g. a mark's
 * circle+content ghost - see {@link markContentAnchorX}).
 *
 * @param {string} ch
 * @param {number} targetGx
 * @param {Record<string, object>} clusters
 * @returns {number}
 */
function charDx(ch, targetGx, clusters) {
  const entry = clusters[ch];
  if (!entry) return targetGx;
  if (entry.glyphs.length > 1) {
    return targetGx - entry.glyphs[entry.glyphs.length - 1].x;
  }
  return targetGx - (entry.glyphs[0]?.x ?? 0);
}

/**
 * Last-resort composition: cluster not resolvable as base+mark (see {@link
 * tryComposeStroke}), so fall back to treating every character as its own
 * independent atom and placing each one's own recorded stroke at its glyph
 * slot - mirrors tools/.../stroke_compose.py's `compose_per_glyph` (the
 * offline bake's equivalent fallback), restricted the same way: only when
 * the character count matches the glyph count, since a mismatch means some
 * character actually contributes more than one glyph (a mark attachment,
 * not independent characters side by side - see that function's docstring
 * for the concretely-verified failure mode of ignoring this).
 *
 * Also bails when any character is a *prefix*-type mark (e.g. െ/േ/ൈ) even
 * though the count matches: HarfBuzz visually reorders a prefix mark's
 * glyph *before* its base's, so glyph index no longer matches character
 * index - see `compose_per_glyph`'s docstring for the concretely-verified
 * "ടെ" failure this avoids (both characters' strokes landing on top of
 * each other at the mark's position).
 *
 * However imperfect the result (no font ligatures, just each atom's own
 * shape offset into place), it's still each atom in the position the font
 * says it belongs - closer to the real word than the plain outline-trace
 * fallback for any cluster where every character actually has its own
 * recorded stroke.
 *
 * @param {string} cluster
 * @param {{ clusters: Record<string, object>, marks: Record<string, object> }} glyphData
 * @returns {{ strokes: {d: string}[] } | null}
 */
function tryComposeFromCharacters(cluster, glyphData) {
  const { clusters, marks } = glyphData;
  const clusterEntry = clusters[cluster];
  const chars = [...cluster];
  if (chars.length < 2 || !clusterEntry || clusterEntry.glyphs.length !== chars.length) return null;
  if (chars.some((ch) => marks?.[ch]?.prefix?.length > 0)) return null;

  const strokes = [];
  for (const [i, ch] of chars.entries()) {
    const sub = STROKE_LIBRARY[ch] ?? tryComposeStroke(ch, glyphData);
    if (!sub?.strokes?.length) return null;
    const g = clusterEntry.glyphs[i];
    const dx = charDx(ch, g.x, clusters);
    for (const s of sub.strokes) strokes.push({ d: offsetSvgPath(s.d, dx, g.y) });
  }

  const entry = { strokes };
  STROKE_LIBRARY[cluster] = entry;
  return entry;
}

/**
 * Resolve `text` into an ordered list of `{ cluster, entry }` pairs.
 *
 * Tries a direct longest-match lookup first, but only at 4/3/2 chars
 * (conjunct+matra → conjunct → consonant+matra) - 1-char is deliberately
 * excluded here even though virama and every matra now have their own
 * `clusters` entry (added so the recorder has a real ghost to record them
 * against, see tools/build_glyph_data.py's `_standalone_inputs()`). A
 * length-1 slice that's *also* a registered mark must get first crack at
 * attaching onto the previously matched segment below - matching it
 * directly here instead would render its isolated dotted-circle-placeholder
 * shape standalone, wrongly splitting it off the consonant it belongs to
 * (e.g. "ദ്യു" as "ദ്യ" + orphaned "ു" instead of one composed cluster).
 *
 * A character with no 4/3/2-length direct match is composed onto the
 * *previously matched* segment (base and mark are adjacent by construction,
 * so "the segment just pushed" is exactly the base this mark attaches to)
 * - see {@link composeMark}. Mark lookup tries a 2-char tail first
 * (subjoined conjunct forms - virama plus a reduced ya/va/la, e.g. "്യ")
 * before falling back to 1-char (virama or a dependent vowel sign alone).
 * Some marks (ു/ൂ/ൃ, and subjoined la) fuse into a glyph unique to the
 * specific preceding consonant in real shaping - composing them generically
 * can't reproduce that exact fused glyph, so they render as the base's own
 * glyph plus the mark's separate standalone shape instead: less tightly
 * kerned than a true font ligature, but still correct and legible (see
 * glyphData.marks / tools/build_glyph_data.py's _build_marks() docstring
 * for the full derivation). Composition is skipped only for marks with a
 * prefix component when the base is more than one glyph - that reordering
 * isn't safe on a non-ligating multi-glyph conjunct.
 *
 * Only once mark composition doesn't apply (no previous segment - start of
 * text - or that unsupported prefix+multi-glyph case) does a length-1
 * direct match get tried, rendering the character's own isolated shape
 * (correct for e.g. a stray mark with nothing to attach to). Failing that,
 * the character is skipped with a console warning.
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
    for (const len of [4, 3, 2]) {
      if (i + len > text.length) continue;
      const slice = text.slice(i, i + len);
      if (!clusters[slice]) continue;
      // A registered mark (e.g. ്ര's own standalone glyph-data entry, kept
      // only so the stroke recorder has a real ghost to record it against
      // - see build_glyph_data.py's _standalone_inputs()) must get first
      // crack at attaching onto the previous segment, exactly like the
      // 1-char virama/matra case below: matching it directly here would
      // render its isolated content+dotted-circle shape standalone in real
      // text instead of composing onto the base it belongs to.
      if (marks[slice] && segs.length > 0) continue;
      segs.push({ cluster: slice, entry: clusters[slice] });
      i += len;
      matched = true;
      break;
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

    const single = text[i];
    if (clusters[single]) {
      segs.push({ cluster: single, entry: clusters[single] });
      i++;
      continue;
    }

    console.warn(`malayalam-stroker: no glyph data for ${JSON.stringify(single)} in ${JSON.stringify(text)} - skipping`);
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
 * @param {{ speed?: number, glyphData?: object, tighten?: number, strokeWidth?: number }} [options]
 * @param {number} [options.speed=6000] - Nominal pen speed in font-units per second.
 * @param {object} [options.glyphData=null] - Pre-loaded glyph data object (skips `load()`).
 * @param {number} [options.tighten=0.06] - Inter-cluster tightening, as a fraction of
 *   unitsPerEm trimmed from each cluster's advance. 0 reproduces the font's raw spacing;
 *   higher values pull characters closer together. See {@link DEFAULT_TIGHTEN_FRACTION}.
 * @param {number} [options.strokeWidth=0.022] - Ink line thickness, as a fraction of
 *   unitsPerEm. See {@link DEFAULT_STROKE_WIDTH_FRACTION}.
 * @param {boolean} [options.outlineOnly=false] - Ignore {@link STROKE_LIBRARY} entirely and
 *   always animate the outer-contour outline fallback, even for clusters with authored
 *   strokes. Useful for a consistent tracing style independent of authoring coverage
 *   (e.g. a wordmark mixing authored and not-yet-authored clusters).
 * @returns {{ load: Function, loadStrokes: Function, play: Function, replay: Function, cancel: Function, destroy: Function, getFallbackClusters: Function }}
 */
export function createStrokeWriter(container, options = {}) {
  const SPEED = options.speed ?? 6000;
  const TIGHTEN = options.tighten ?? DEFAULT_TIGHTEN_FRACTION;
  const STROKE_WIDTH_FRACTION = options.strokeWidth ?? DEFAULT_STROKE_WIDTH_FRACTION;
  const OUTLINE_ONLY = options.outlineOnly ?? false;
  const state = { playToken: 0, lastFallbackClusters: [] };
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
   * A missing file (404 or network error) is silently ignored - the library
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
   * ghost rendering and outline fallback - authored strokes fire once per
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
   * @returns {{ glyphUnits: object[], stylus: SVGCircleElement, fallbackClusters: string[] }}
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

    const sw = unitsPerEm * STROKE_WIDTH_FRACTION;
    const stylus = svgEl("circle", { class: "ms-stylus", r: unitsPerEm * 0.016 });
    stylus.style.opacity = "0";
    svg.appendChild(stylus);

    const fallbackClusters = [];
    const glyphUnits = segGroups.map((grp) => {
      const authored = OUTLINE_ONLY
        ? null
        : (STROKE_LIBRARY[grp.cluster] ??
           tryComposeStroke(grp.cluster, glyphData) ??
           tryComposeFromCharacters(grp.cluster, glyphData));

      // Only a genuine gap when outline-only wasn't explicitly requested -
      // OUTLINE_ONLY always skips STROKE_LIBRARY by design, so that's not
      // something to flag as missing handwriting data.
      if (!OUTLINE_ONLY && !authored?.strokes?.length) fallbackClusters.push(grp.cluster);

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

    return { glyphUnits, stylus, fallbackClusters };
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
   * Build the stage and trace `text` through it once.
   *
   * @param {string} text
   * @param {number} speedMul
   * @param {number} token
   * @returns {Promise<void>}
   */
  async function playOnce(text, speedMul, token) {
    const trace = buildTrace(text);
    if (!trace) return;
    const { glyphUnits, stylus, fallbackClusters } = buildStage(trace);
    state.lastFallbackClusters = fallbackClusters;
    if (fallbackClusters.length) {
      console.warn(
        `malayalam-stroker: no handwriting data for ${fallbackClusters.map((c) => JSON.stringify(c)).join(", ")} in ${JSON.stringify(text)} - showing an approximated outline trace instead`
      );
    }

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
   * Animate `text` from scratch.
   *
   * Calls `load()` automatically if glyph data has not been loaded yet.
   *
   * @param {string} text - Malayalam (or any supported script) text.
   * @param {{ speed?: number, count?: number }} [playOptions]
   * @param {number} [playOptions.speed=1] - Speed multiplier (>1 = faster).
   * @param {number} [playOptions.count=1] - Number of times to trace `text` in a row,
   *   pausing {@link REPLAY_PAUSE_MS} between repeats. A new `play()`/`replay()` call,
   *   or `cancel()`, stops the sequence before its next repeat.
   * @returns {Promise<void>}
   */
  async function play(text, playOptions = {}) {
    if (!glyphData) await load();
    lastText = text;
    const speedMul = playOptions.speed ?? 1;
    const count = Math.max(1, playOptions.count ?? 1);
    const token = ++state.playToken;

    for (let i = 0; i < count; i++) {
      if (token !== state.playToken) return;
      await playOnce(text, speedMul, token);
      if (i < count - 1 && token === state.playToken) {
        await new Promise((r) => setTimeout(r, REPLAY_PAUSE_MS));
      }
    }
  }

  /**
   * Replay the last traced text.
   *
   * @param {{ speed?: number, count?: number }} [options]
   * @returns {Promise<void>}
   */
  function replay(options = {}) {
    return lastText ? play(lastText, options) : Promise.resolve();
  }

  /** Cancel any in-progress animation immediately. */
  function cancel() {
    state.playToken++;
  }

  /**
   * Clusters from the most recent `play()`/`replay()` call that had no
   * authored (or composable-from-authored) handwriting data and fell back
   * to an outline trace instead - i.e. an approximation of the printed
   * glyph's own border, not real handwriting motion. Empty when every
   * cluster in the last-played text had real stroke data, or before any
   * `play()` call has completed.
   *
   * Use this to tell users a trace is only an approximation for part of a
   * word, e.g. `if (writer.getFallbackClusters().length) { ...show a note... }`.
   *
   * @returns {string[]}
   */
  function getFallbackClusters() {
    return state.lastFallbackClusters;
  }

  /** Cancel animation and remove all DOM nodes from `container`. */
  function destroy() {
    cancel();
    container.innerHTML = "";
    lastText = null;
  }

  return { load, loadStrokes, play, replay, cancel, destroy, getFallbackClusters };
}

/**
 * Internal functions exposed only for unit testing (see tests/index.test.js).
 * Not part of the public API - no stability guarantee, may change shape or
 * disappear without notice. Use {@link createStrokeWriter} for real usage.
 */
export const _internal = {
  composeMark,
  resolveGhostEntry,
  offsetSvgPath,
  SPLIT_VOWEL_PARTS,
  markContentAnchorX,
  applyMarkStroke,
  applySequentialMarkStrokes,
  tryDirectMarkStroke,
  tryComposeStroke,
  charDx,
  tryComposeFromCharacters,
  resolveSegments,
};


