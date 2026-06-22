/**
 * malayalam-stroker (JS)
 *
 * What you see: the ghost letter is already there (faint). A pen moves
 * along its natural curves and solid ink appears in its wake — exactly
 * like writing over a pencil sketch with ink. No border line. No stroke
 * outline. Just the filled letter growing as the pen moves.
 *
 * How it works: a thick round brush sweeps along the glyph's contour
 * as an SVG mask. The brush is invisible — it only controls which part
 * of the solid fill is visible. As the brush moves, more of the solid
 * fill is revealed. The glowing stylus dot rides at the brush tip.
 *
 * START_OVERRIDES (for coders, not end-users):
 * Set this object before calling play() to control where each glyph
 * starts. Key = glyphName (log trace.glyphs.map(g=>g.glyphName) to
 * find the names for your font). Value = one of:
 *   "leftmost" | "rightmost" | "topmost" | "bottommost"
 *   OR a number 0..1 (fraction along path arc-length)
 *   OR an array of the above, one per sub-contour
 *
 * Example:
 *   import { createStrokeWriter, START_OVERRIDES } from "malayalam-stroker";
 *   START_OVERRIDES["n1"] = "topmost";
 *   START_OVERRIDES["k1sh"] = [0.25, "leftmost"];
 *   const writer = createStrokeWriter(container);
 *   await writer.play(trace);
 */

const SVGNS = "http://www.w3.org/2000/svg";
const SAMPLE_STEPS = 140;   // polyline resolution for start-point rotation
const PEN_LIFT_MS  = 80;    // pause between sub-contours (pen lifts between strokes)

/**
 * Per-glyph start-point overrides. Edit this object in code — it's not
 * exposed in any UI. The right start point is the one that matches how
 * you'd pick up a pen and naturally begin that letter.
 */
export const START_OVERRIDES = {};

/* ── helpers ──────────────────────────────────────────────────────── */

function svgEl(tag, attrs) {
  const el = document.createElementNS(SVGNS, tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  return el;
}

function splitSubpaths(d) {
  return d.match(/M[^M]*/g) ?? [d];
}

function resolveOverride(glyphName, subIndex) {
  const entry = START_OVERRIDES[glyphName];
  if (entry === undefined) return "leftmost";
  if (Array.isArray(entry)) return entry[subIndex] ?? "leftmost";
  return entry;
}

/**
 * Resample `pathEl` into SAMPLE_STEPS points, rotate so the chosen
 * start point is first, return the resulting polyline as a 'd' string.
 * Only used for the invisible mask brush — the visible fill keeps the
 * original bezier path.
 */
function rotatedPolyline(pathEl, override) {
  const len = pathEl.getTotalLength();
  if (len <= 0) return pathEl.getAttribute("d");

  const pts = Array.from({ length: SAMPLE_STEPS }, (_, i) =>
    pathEl.getPointAtLength((i / SAMPLE_STEPS) * len)
  );

  let startIdx = 0;
  if (typeof override === "number") {
    startIdx = Math.round(override * SAMPLE_STEPS) % SAMPLE_STEPS;
  } else {
    const axis    = { leftmost:"x", rightmost:"x", topmost:"y", bottommost:"y" }[override] ?? "x";
    const prefer  = (override === "rightmost" || override === "bottommost")
                    ? (a, b) => a > b : (a, b) => a < b;
    let best = pts[0][axis];
    for (let i = 1; i < pts.length; i++) {
      if (prefer(pts[i][axis], best)) { best = pts[i][axis]; startIdx = i; }
    }
  }

  const rot = [...pts.slice(startIdx), ...pts.slice(0, startIdx)];
  return "M " + rot.map(p => `${p.x} ${p.y}`).join(" L ") + " Z";
}

/* ── main export ──────────────────────────────────────────────────── */

export function createStrokeWriter(container, options = {}) {
  // font-units of contour length revealed per second — tune to taste
  const SPEED = options.speed ?? 8000;

  const state = { playToken: 0 };
  let idSeed = 0;
  let lastTrace = null;

  /* Build the full SVG stage for one trace ────────────────────────── */
  function buildStage(trace) {
    container.innerHTML = "";
    const { unitsPerEm, ascent, descent, totalAdvance, glyphs } = trace;
    const pad = unitsPerEm * 0.1;
    const vb  = { x:-pad, y:-ascent-pad, w:totalAdvance+pad*2, h:ascent-descent+pad*2 };

    const svg = svgEl("svg", { viewBox:`${vb.x} ${vb.y} ${vb.w} ${vb.h}` });

    // Ghost: full word, always visible, acts as the tracing guide
    const ghostG = svgEl("g", { class:"ms-ghost" });
    glyphs.forEach(g => ghostG.appendChild(
      svgEl("path", { d:g.d, transform:`translate(${g.x},${g.y})` })
    ));
    svg.appendChild(ghostG);

    const defs = svgEl("defs", {});
    svg.appendChild(defs);

    // Attach to DOM NOW — getBBox / getTotalLength need a live document
    container.appendChild(svg);

    // Scratch element for measurements (never rendered visually)
    const scratch = svgEl("path", {});
    defs.appendChild(scratch);

    // Stylus dot — rides at the leading edge of the brush
    const stylus = svgEl("circle", { class:"ms-stylus", r: unitsPerEm * 0.016 });
    stylus.style.opacity = "0";
    svg.appendChild(stylus);

    /* Per-glyph build ─────────────────────────────────────────────── */
    const glyphUnits = glyphs.map(g => {
      const gEl     = svgEl("g", { transform:`translate(${g.x},${g.y})` });
      const fillEl  = svgEl("path", { d:g.d, class:"ms-fill" });

      // Mask: thick round brush sweeps the contour, revealing the fill
      const maskId  = `ms-mask-${idSeed++}`;
      const maskEl  = svgEl("mask", { id:maskId, maskUnits:"userSpaceOnUse" });
      defs.appendChild(maskEl);
      fillEl.setAttribute("mask", `url(#${maskId})`);

      gEl.appendChild(fillEl);
      svg.appendChild(gEl);

      // Brush width = big enough to cover the full interior on one sweep.
      // getBBox() works now because svg is already in the document.
      const bbox       = fillEl.getBBox();
      const brushWidth = Math.max(bbox.width, bbox.height) * 1.7 || unitsPerEm * 0.3;

      const subDs = splitSubpaths(g.d);

      const subUnits = subDs.map((subD, i) => {
        // Build rotated polyline using scratch element
        scratch.setAttribute("d", subD);
        const override  = resolveOverride(g.glyphName, i);
        const rotatedD  = rotatedPolyline(scratch, override);

        const brush = svgEl("path", {
          d: rotatedD, stroke:"white", fill:"none",
          "stroke-linecap":"round", "stroke-linejoin":"round",
        });
        brush.setAttribute("stroke-width", brushWidth);
        maskEl.appendChild(brush);

        const len = brush.getTotalLength();

        // Start fully hidden — no ink until this sub-contour's turn
        if (len > 0) {
          brush.setAttribute("stroke-dasharray",  `${len} ${len}`);
          brush.setAttribute("stroke-dashoffset", String(len));
        }

        return { brush, len };
      });

      return { gEl, fillEl, subUnits };
    });

    return { glyphUnits, stylus };
  }

  /* Animate one sub-contour ─────────────────────────────────────────
   * Sweeps dashoffset from len → 0, moving the stylus dot along the
   * leading edge. No stroke drawn on screen — only the mask moves.    */
  function revealSub(subUnit, stylus, glyphTranslate, durationMs, token) {
    return new Promise(resolve => {
      const { brush, len } = subUnit;
      if (len <= 0) return resolve();

      // Stylus starts at point 0 of the rotated polyline
      const p0 = brush.getPointAtLength(0);
      stylus.setAttribute("cx", String(p0.x + glyphTranslate.x));
      stylus.setAttribute("cy", String(p0.y + glyphTranslate.y));
      stylus.style.opacity = "1";

      const start = performance.now();
      function frame(now) {
        if (token !== state.playToken) return resolve();
        const t   = Math.max(0, Math.min(1, (now - start) / durationMs));
        brush.setAttribute("stroke-dashoffset", String(len * (1 - t)));

        // Move stylus dot to current pen tip position
        const pt = brush.getPointAtLength(t * len);
        stylus.setAttribute("cx", String(pt.x + glyphTranslate.x));
        stylus.setAttribute("cy", String(pt.y + glyphTranslate.y));

        if (t < 1) requestAnimationFrame(frame);
        else resolve();
      }
      requestAnimationFrame(frame);
    });
  }

  /* Animate one glyph (all its sub-contours, in sequence) ─────────── */
  async function revealGlyph(unit, stylus, durationMs, token) {
    const { gEl, subUnits } = unit;

    // Parse the glyph's translate so we can position the stylus in SVG coords
    const xform = gEl.getAttribute("transform") ?? "";
    const m = xform.match(/translate\(([^,)]+)[, ]+([^)]+)\)/);
    const translate = m ? { x: parseFloat(m[1]), y: parseFloat(m[2]) } : { x:0, y:0 };

    const totalLen = subUnits.reduce((s, u) => s + u.len, 0) || 1;

    for (const sub of subUnits) {
      if (token !== state.playToken) return;
      const subDuration = Math.max(80, durationMs * (sub.len / totalLen));
      await revealSub(sub, stylus, translate, subDuration, token);
      if (sub !== subUnits[subUnits.length - 1]) {
        // Pen lift between sub-contours
        stylus.style.opacity = "0";
        await new Promise(r => setTimeout(r, PEN_LIFT_MS));
      }
    }
    stylus.style.opacity = "0";
  }

  /* Public API ──────────────────────────────────────────────────────── */

  async function play(trace, playOptions = {}) {
    lastTrace = trace;
    const speedMult = playOptions.speed ?? 1;
    const token     = ++state.playToken;
    const { glyphUnits, stylus } = buildStage(trace);

    for (const unit of glyphUnits) {
      if (token !== state.playToken) return;
      const totalLen   = unit.subUnits.reduce((s, u) => s + u.len, 0) || 1;
      const duration   = Math.max(200, (totalLen / (SPEED * speedMult)) * 1000);
      await revealGlyph(unit, stylus, duration, token);
    }
    if (token === state.playToken) stylus.style.opacity = "0";
  }

  function replay(playOptions = {}) {
    return lastTrace ? play(lastTrace, playOptions) : Promise.resolve();
  }

  function cancel() { state.playToken++; }

  function destroy() { cancel(); container.innerHTML = ""; lastTrace = null; }

  return { play, replay, cancel, destroy };
}
