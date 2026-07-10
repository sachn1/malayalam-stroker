import js from "@eslint/js";

const browserGlobals = {
  window: "readonly",
  document: "readonly",
  console: "readonly",
  fetch: "readonly",
  URL: "readonly",
  navigator: "readonly",
  requestAnimationFrame: "readonly",
  performance: "readonly",
  setTimeout: "readonly",
  clearTimeout: "readonly",
  FileReader: "readonly",
  Blob: "readonly",
  alert: "readonly",
  confirm: "readonly",
  SVGElement: "readonly",
  SVGSVGElement: "readonly",
  SVGPathElement: "readonly",
};

export default [
  js.configs.recommended,
  {
    // Event-handler callbacks (onPointerUp, etc.) commonly take an event
    // param purely to match the addEventListener callback signature, even
    // when the handler itself doesn't read it — not worth flagging.
    rules: {
      "no-unused-vars": ["error", { args: "none" }],
    },
  },
  {
    // js/src: published ES module library.
    files: ["js/src/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: browserGlobals,
    },
  },
  {
    // demo/demo.js: ES module (loaded via <script type="module">).
    files: ["demo/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: browserGlobals,
    },
  },
  {
    // tools/stroke-recorder.js: classic (non-module) script.
    files: ["tools/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: browserGlobals,
    },
  },
  {
    // tests/: vitest test files (Node, ES modules).
    files: ["tests/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: { console: "readonly" },
    },
  },
];
