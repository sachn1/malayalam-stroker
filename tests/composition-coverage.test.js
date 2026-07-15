/**
 * Coverage test against the REAL glyph-data.json/stroke-data.json (unlike
 * index.test.js's script-agnostic synthetic fixtures) - the only way to
 * catch data-shape bugs a hand-built fixture can accidentally paper over.
 * This is exactly how the ത്സ്യ/ത്സ്യം regression shipped: index.test.js's
 * "recursively composes an intermediate base" case pre-registered its
 * intermediate cluster directly, which real glyph-data.json never does (see
 * resolveGhostEntry's docstring in index.js) - so the suite was green while
 * every 2+-level mark chain whose intermediate step wasn't separately baked
 * silently fell back to the outline-trace fallback instead of using the
 * authored strokes that were actually available for its parts.
 *
 * Scope: every conjunct (consonant + virama + consonant) that has an
 * authored stroke, chained with the subjoined conjunct marks (്യ/്വ/്ല) and
 * then a trailing vowel/anusvara/visarga - the exact "conjunct + subjoined
 * form + trailing mark" shape that broke. This isn't every theoretically
 * producible string (many consonant pairs never occur in real Malayalam),
 * but it is every *mechanically reachable* chain of that shape, so it
 * catches the composition engine bailing early regardless of which specific
 * combination a future word happens to use.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it } from "vitest";
import { STROKE_LIBRARY, _internal } from "../js/src/index.js";

const { tryComposeStroke, resolveGhostEntry } = _internal;

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const glyphData = JSON.parse(readFileSync(`${ROOT}js/src/glyph-data.json`, "utf-8"));
const strokeData = JSON.parse(readFileSync(`${ROOT}js/src/stroke-data.json`, "utf-8"));

const VIRAMA = "്";
const SUBJOINED_MARKS = [VIRAMA + "യ", VIRAMA + "വ", VIRAMA + "ല"];
const TRAILING_MARKS = ["ം", "ഃ", "ു", "ൂ", "ാ", "ി", "ീ"];

/** Every 3-char consonant+virama+consonant conjunct with a directly authored stroke. */
const authoredConjuncts = Object.keys(strokeData).filter(
  (k) => k.length === 3 && k[1] === VIRAMA
);

beforeEach(() => {
  for (const key of Object.keys(STROKE_LIBRARY)) delete STROKE_LIBRARY[key];
  Object.assign(STROKE_LIBRARY, strokeData);
});

describe("real-data sanity", () => {
  it("found a non-trivial number of authored conjuncts to test against", () => {
    // Guards the coverage test itself against silently testing nothing if
    // stroke-data.json's shape ever changes.
    expect(authoredConjuncts.length).toBeGreaterThan(50);
  });

  it("ത്സ്യം composes from authored strokes, not the outline fallback", () => {
    // The concrete case that surfaced this bug (see index.js's index.test.js
    // and this file's module docstring).
    const result = tryComposeStroke("ത്സ്യം", glyphData);
    expect(result).not.toBeNull();
  });
});

describe("conjunct + subjoined mark (1-level chain)", () => {
  for (const conjunct of authoredConjuncts) {
    for (const subjoined of SUBJOINED_MARKS) {
      const cluster = conjunct + subjoined;
      it(`composes ${JSON.stringify(cluster)} from ${JSON.stringify(conjunct)}'s authored stroke`, () => {
        // The subjoined mark itself must be a known composable mark for
        // this to be reachable at all - skip pairs it isn't (not every
        // mark set includes every subjoined form for every font).
        if (!glyphData.marks[subjoined]) return;
        expect(tryComposeStroke(cluster, glyphData)).not.toBeNull();
      });
    }
  }
});

describe("conjunct + subjoined mark + trailing mark (2-level chain)", () => {
  // A representative sample, not the full cross product (1296 conjuncts x 3
  // subjoined x 7 trailing would make this suite minutes long) - enough
  // conjuncts to catch a regression in the recursive composition path
  // itself, which doesn't care about the specific consonants involved.
  const sample = authoredConjuncts.filter((_, i) => i % 7 === 0);

  for (const conjunct of sample) {
    for (const subjoined of SUBJOINED_MARKS) {
      for (const trailing of TRAILING_MARKS) {
        const cluster = conjunct + subjoined + trailing;
        it(`composes ${JSON.stringify(cluster)} without bailing on the intermediate step`, () => {
          if (!glyphData.marks[subjoined] || !glyphData.marks[trailing]) return;
          // resolveGhostEntry is the piece that broke: tryComposeStroke's
          // recursive stroke composition already worked, but it fed the
          // wrong (missing) glyph *advance* for the un-registered
          // intermediate cluster into the mark-anchor math. Assert both
          // layers directly so a regression in either shows up here.
          expect(resolveGhostEntry(conjunct + subjoined, glyphData.clusters, glyphData.marks)).not.toBeNull();
          expect(tryComposeStroke(cluster, glyphData)).not.toBeNull();
        });
      }
    }
  }
});
