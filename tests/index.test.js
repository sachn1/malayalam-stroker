/**
 * Tests for js/src/index.js's segmentation/composition engine, via the
 * `_internal` test-only export bundle (see index.js's bottom).
 *
 * Deliberately script-agnostic: fixtures use synthetic single-letter
 * "clusters" (A, B, s) shaped like glyph-data.json entries, never real
 * Malayalam clusters. The engine only cares about character/glyph counts
 * and x/y offsets - a new script's stroke pipeline should never need to
 * touch this file. The one exception is the SPLIT_VOWEL_PARTS test, which
 * is explicitly checking Malayalam-specific decomposition data.
 *
 * DOM-dependent parts of index.js (buildStage, animation timing) aren't
 * covered here - they need real SVG geometry APIs (getTotalLength etc.)
 * that jsdom doesn't implement; verify those via the `run` skill or a
 * manual browser check instead.
 */

import { beforeEach, describe, expect, it } from "vitest";
import { STROKE_LIBRARY, _internal } from "../js/src/index.js";

const {
  composeMark,
  offsetSvgPath,
  SPLIT_VOWEL_PARTS,
  markContentAnchorX,
  applyMarkStroke,
  applySequentialMarkStrokes,
  tryComposeStroke,
  charDx,
  tryComposeFromCharacters,
  resolveSegments,
} = _internal;

beforeEach(() => {
  for (const key of Object.keys(STROKE_LIBRARY)) delete STROKE_LIBRARY[key];
});

describe("offsetSvgPath", () => {
  it("returns the exact same reference for a zero offset", () => {
    const d = "M0 0 L10 10";
    expect(offsetSvgPath(d, 0, 0)).toBe(d);
  });

  it("shifts M/L coordinate pairs", () => {
    expect(offsetSvgPath("M0 0 L10 10", 5, 3)).toBe("M 5.0 3.0 L 15.0 13.0");
  });

  it("shifts H/V single-axis commands on their own axis only", () => {
    expect(offsetSvgPath("M0 0 H10 V20", 5, 3)).toBe("M 5.0 3.0 H 15.0 V 23.0");
  });
});

describe("composeMark", () => {
  const base = { glyphs: [{ d: "Mbase", x: 0, y: 0 }], advance: 100 };

  it("appends a suffix mark's glyph after the base's advance", () => {
    const suffixMark = { shift: 0, prefix: [], suffix: [{ d: "Msuf", x: 0, y: 0 }], trailingWidth: 20 };
    const result = composeMark(base, suffixMark);
    expect(result.glyphs).toEqual([
      { d: "Mbase", x: 0, y: 0 },
      { d: "Msuf", x: 100, y: 0 },
    ]);
    expect(result.advance).toBe(120);
  });

  it("prepends a prefix mark's glyph and shifts the base by its own shift", () => {
    const prefixMark = { shift: 15, prefix: [{ d: "Mpre", x: 0, y: 0 }], suffix: [], trailingWidth: 0 };
    const result = composeMark(base, prefixMark);
    expect(result.glyphs).toEqual([
      { d: "Mpre", x: 0, y: 0 },
      { d: "Mbase", x: 15, y: 0 },
    ]);
    expect(result.advance).toBe(115);
  });
});

describe("markContentAnchorX", () => {
  const clusters = {
    A: { glyphs: [{ x: 0, y: 0 }], advance: 100 },
    M: { glyphs: [{ x: 0, y: 0 }, { x: 30, y: 0 }], advance: 100 },
  };

  it("returns 0 for a plain single-glyph character", () => {
    expect(markContentAnchorX("A", clusters)).toBe(0);
  });

  it("returns the last glyph's x for a mark-like 2-glyph standalone entry", () => {
    expect(markContentAnchorX("M", clusters)).toBe(30);
  });

  it("returns 0 for a character with no clusters entry at all", () => {
    expect(markContentAnchorX("Z", clusters)).toBe(0);
  });
});

describe("applyMarkStroke", () => {
  it("rejects a compound mark (both prefix and suffix)", () => {
    const compoundMark = {
      shift: 5,
      prefix: [{ d: "p", x: 0, y: 0 }],
      suffix: [{ d: "s", x: 0, y: 0 }],
      trailingWidth: 10,
    };
    const result = applyMarkStroke([{ d: "M0 0" }], compoundMark, [{ d: "Mmark" }], 100);
    expect(result).toBeNull();
  });

  it("applies a suffix mark's anchor correction, matching the Python engine's convention", () => {
    // Mirrors python/tests/test_stroke_compose.py's mark-anchor-correction case exactly.
    const mark = { shift: 0, prefix: [], suffix: [{ d: "s", x: 0, y: 0 }], trailingWidth: 0 };
    const result = applyMarkStroke([{ d: "M5 5" }], mark, [{ d: "M30 0" }], 100, 30);
    expect(result.strokes).toEqual([{ d: "M5 5" }, { d: "M 100.0 0.0" }]);
  });
});

describe("tryComposeStroke", () => {
  const clusters = {
    A: { glyphs: [{ d: "gA", x: 0, y: 0 }], advance: 100 },
    s: { glyphs: [{ d: "circle", x: 0, y: 0 }, { d: "content", x: 30, y: 0 }], advance: 50 },
  };
  const marks = {
    s: { shift: 0, prefix: [], suffix: [{ d: "Msuf", x: 0, y: 0 }], trailingWidth: 20 },
  };
  const glyphData = { clusters, marks };

  beforeEach(() => {
    STROKE_LIBRARY.A = { strokes: [{ d: "M5 5 L15 5" }] };
    STROKE_LIBRARY.s = { strokes: [{ d: "M30 0 L35 0" }] };
  });

  it("composes base + suffix mark with the anchor correction applied", () => {
    const result = tryComposeStroke("As", glyphData);
    expect(result.strokes).toEqual([
      { d: "M5 5 L15 5" },
      { d: "M 100.0 0.0 L 105.0 0.0" },
    ]);
  });

  it("caches the composed result into STROKE_LIBRARY", () => {
    tryComposeStroke("As", glyphData);
    expect(STROKE_LIBRARY.As).toBeDefined();
  });

  it("returns null when the base has no recorded stroke", () => {
    delete STROKE_LIBRARY.A;
    expect(tryComposeStroke("As", glyphData)).toBeNull();
  });

  it("recursively composes an intermediate base that isn't cached yet", () => {
    // "ABs": base "AB" isn't itself in STROKE_LIBRARY, but is composable
    // from "A" + suffix mark "B" -- this is the exact shape of bug fixed
    // for ദ്യു (a mark chain more than one level deep).
    //
    // Deliberately NOT pre-registering "AB" in `deepClusters` here, matching
    // real glyph-data.json's shape: build_glyph_data.py never bakes
    // intermediate composed clusters as their own direct entries (only
    // atoms - single/direct clusters - and their composable marks are
    // baked; see resolveGhostEntry's docstring in index.js). A fixture that
    // pre-registers "AB" tests the stroke-recursion path only, and would
    // pass even if the *glyph*-entry lookup for the intermediate base falls
    // back to a bare `clusters[baseKey]` lookup instead of composing it -
    // exactly the bug that shipped for ത്സ്യ/ത്സ്യം (see resolveGhostEntry).
    const deepClusters = {
      ...clusters,
      B: { glyphs: [{ d: "circle", x: 0, y: 0 }, { d: "content", x: 10, y: 0 }], advance: 40 },
    };
    const deepMarks = {
      ...marks,
      B: { shift: 0, prefix: [], suffix: [{ d: "Bsuf", x: 0, y: 0 }], trailingWidth: 40 },
    };
    STROKE_LIBRARY.B = { strokes: [{ d: "M10 0 L20 0" }] };
    const result = tryComposeStroke("ABs", { clusters: deepClusters, marks: deepMarks });
    expect(result).not.toBeNull();
    expect(STROKE_LIBRARY.AB).toBeDefined(); // intermediate base got cached too
  });
});

describe("applySequentialMarkStrokes (compound vowel decomposition)", () => {
  it("applies each split part in order, chaining advance forward", () => {
    const clusters = {};
    const marks = {
      e: { shift: 50, prefix: [{ d: "e-glyph", x: 0, y: 0 }], suffix: [], trailingWidth: 0 },
      a: { shift: 0, prefix: [], suffix: [{ d: "a-glyph", x: 0, y: 0 }], trailingWidth: 10 },
    };
    STROKE_LIBRARY.e = { strokes: [{ d: "M0 0" }] };
    STROKE_LIBRARY.a = { strokes: [{ d: "M0 0" }] };

    const result = applySequentialMarkStrokes([{ d: "Mbase" }], 100, ["e", "a"], marks, clusters);
    expect(result).not.toBeNull();
    // advance: after "e" (prefix, shift=50): 50+100+0=150; after "a" (suffix): 0+150+10=160
    expect(result.advance).toBe(160);
  });

  it("returns null if any part in the chain has no recorded stroke", () => {
    const marks = { e: { shift: 0, prefix: [{ d: "x" }], suffix: [], trailingWidth: 0 } };
    const result = applySequentialMarkStrokes([{ d: "Mbase" }], 100, ["e"], marks, {});
    expect(result).toBeNull();
  });
});

describe("SPLIT_VOWEL_PARTS", () => {
  it("matches the documented Unicode canonical decomposition for ൊ/ോ/ൌ", () => {
    expect(SPLIT_VOWEL_PARTS).toEqual({
      "ൊ": ["െ", "ാ"],
      "ോ": ["േ", "ാ"],
      "ൌ": ["െ", "ൗ"],
    });
  });
});

describe("charDx", () => {
  const clusters = {
    A: { glyphs: [{ x: 0, y: 0 }], advance: 100 },
    M: { glyphs: [{ x: 0, y: 0 }, { x: 30, y: 0 }], advance: 100 },
  };

  it("uses the raw target for a simple single-glyph character", () => {
    expect(charDx("A", 250, clusters)).toBe(250);
  });

  it("subtracts the content anchor for a mark-like character", () => {
    expect(charDx("M", 100, clusters)).toBe(70);
  });

  it("falls back to the raw target for an unknown character", () => {
    expect(charDx("Z", 42, clusters)).toBe(42);
  });
});

describe("tryComposeFromCharacters", () => {
  const clusters = {
    A: { glyphs: [{ x: 0, y: 0 }], advance: 100 },
    B: { glyphs: [{ x: 0, y: 0 }], advance: 100 },
    AB: { glyphs: [{ x: 0, y: 0 }, { x: 100, y: 0 }], advance: 200 },
    AB3: { glyphs: [{ x: 0, y: 0 }, { x: 50, y: 0 }, { x: 100, y: 0 }], advance: 200 },
  };

  beforeEach(() => {
    STROKE_LIBRARY.A = { strokes: [{ d: "M5 5 L15 5" }] };
    STROKE_LIBRARY.B = { strokes: [{ d: "M2 2 L12 2" }] };
  });

  it("composes two simple characters at their own glyph slots", () => {
    const result = tryComposeFromCharacters("AB", { clusters });
    expect(result.strokes).toEqual([
      { d: "M5 5 L15 5" },
      { d: "M 102.0 2.0 L 112.0 2.0" },
    ]);
  });

  it("returns null when char count and glyph count mismatch", () => {
    expect(tryComposeFromCharacters("AB3", { clusters })).toBeNull();
  });

  it("returns null when a component has no recorded stroke", () => {
    delete STROKE_LIBRARY.B;
    expect(tryComposeFromCharacters("AB", { clusters })).toBeNull();
  });

  it("returns null when a character is a prefix-type mark", () => {
    // Regression test for "ടെ": HarfBuzz visually reorders a prefix mark's
    // glyph before its base's, so glyph index no longer matches character
    // index - composing it lockstep put both strokes on top of each other.
    const marks = { B: { prefix: [{ d: "M0 0", x: 0, y: 0 }] } };
    expect(tryComposeFromCharacters("AB", { clusters, marks })).toBeNull();
  });

  it("composes normally when a character's mark is suffix-only", () => {
    const marks = { B: { prefix: [], suffix: [{ d: "M0 0", x: 0, y: 0 }] } };
    expect(tryComposeFromCharacters("AB", { clusters, marks })).not.toBeNull();
  });
});

describe("resolveSegments", () => {
  it("matches a direct multi-character cluster as one segment", () => {
    const clusters = { AB: { glyphs: [{ d: "g", x: 0, y: 0 }], advance: 100 } };
    const segs = resolveSegments("AB", clusters, {});
    expect(segs.map((s) => s.cluster)).toEqual(["AB"]);
  });

  it("prefers mark composition over a mark's own standalone direct match", () => {
    // "s" is BOTH a registered mark AND has its own standalone cluster
    // entry (mimicking virama/matras after they got standalone ghosts) --
    // this exact shape caused a real dotted-circle-placeholder regression:
    // resolveSegments must merge "A"+"s" into one segment, not split off
    // "s" as its own isolated standalone match.
    const clusters = {
      A: { glyphs: [{ d: "gA", x: 0, y: 0 }], advance: 100 },
      s: { glyphs: [{ d: "circle", x: 0, y: 0 }, { d: "content", x: 30, y: 0 }], advance: 50 },
    };
    const marks = {
      s: { shift: 0, prefix: [], suffix: [{ d: "Msuf", x: 0, y: 0 }], trailingWidth: 20 },
    };
    const segs = resolveSegments("As", clusters, marks);
    expect(segs.map((s) => s.cluster)).toEqual(["As"]);
  });

  it("falls back to a mark's own standalone match when there's no previous segment", () => {
    const clusters = {
      s: { glyphs: [{ d: "circle", x: 0, y: 0 }, { d: "content", x: 30, y: 0 }], advance: 50 },
    };
    const marks = {
      s: { shift: 0, prefix: [], suffix: [{ d: "Msuf", x: 0, y: 0 }], trailingWidth: 20 },
    };
    const segs = resolveSegments("s", clusters, marks);
    expect(segs.map((s) => s.cluster)).toEqual(["s"]);
  });

  it("prefers mark composition over a *multi-character* mark's own standalone match", () => {
    // Same shape as the single-char "s" case above, but with a 2-char mark
    // key (mirrors ്ര - VIRAMA + "ര" - getting its own standalone
    // glyph-data entry so the recorder has a real ghost to record against;
    // see build_glyph_data.py's _standalone_inputs()). The direct-match
    // loop above checks lengths [4, 3, 2], unlike the always-mark-first
    // 1-char fallback at the very bottom of this function - so a 2-char
    // mark needs its own guard, not just the 1-char one already covered.
    // Regression: real text like ചന്ദ്രൻ used to split "mr" off as its own
    // isolated standalone match (dotted-circle glyph included) instead of
    // composing onto "AB", the base it belongs to.
    const clusters = {
      A: { glyphs: [{ d: "gA", x: 0, y: 0 }], advance: 100 },
      B: { glyphs: [{ d: "gB", x: 0, y: 0 }], advance: 80 },
      AB: { glyphs: [{ d: "gA", x: 0, y: 0 }, { d: "gB", x: 100, y: 0 }], advance: 180 },
      mr: { glyphs: [{ d: "circle", x: 0, y: 0 }, { d: "content", x: 30, y: 0 }], advance: 50 },
    };
    const marks = {
      mr: { shift: 0, prefix: [], suffix: [{ d: "Msuf", x: 0, y: 0 }], trailingWidth: 20 },
    };
    const segs = resolveSegments("ABmr", clusters, marks);
    expect(segs.map((s) => s.cluster)).toEqual(["ABmr"]);
  });

  it("warns and skips a character with no cluster or mark match at all", () => {
    const consoleWarn = console.warn;
    const warnings = [];
    console.warn = (msg) => warnings.push(msg);
    try {
      const segs = resolveSegments("?", {}, {});
      expect(segs).toEqual([]);
      expect(warnings).toHaveLength(1);
    } finally {
      console.warn = consoleWarn;
    }
  });
});
