/**
 * Inertia rules — the seam between a Laravel backend and its bundled frontend.
 *
 * Both rules here guard the same failure: the seam is the one place where backend and
 * frontend assumptions can drift silently. A route renamed in PHP does not break a
 * hardcoded URL string in TSX until a user clicks it, and a model passed straight into
 * props ships every column — including the ones added later by someone who never
 * looked at this page.
 */

const FRONTEND = /\.(ts|tsx|js|jsx)$/;
const PHP = /\.php$/;

export const inertiaRules = [
  {
    id: 'inertia/no-hardcoded-route',
    stack: 'inertia',
    files: FRONTEND,
    skip: (ctx) => ctx.isTest,
    custom: (lines, i) => {
      const match = /\b(router|Inertia)\.(get|post|put|patch|delete|visit|reload)\s*\(\s*(['"`])(\/[^'"`]*)/.exec(lines[i]);
      if (!match) return false;
      // Wayfinder helpers return objects, not strings; only a literal path is a problem.
      return !/^\/\//.test(match[4]);
    },
    message:
      'A hardcoded URL here does not move when the route does. Use the generated Wayfinder helper for the route (`import { store } from "@/routes/..."`).',
    doc: 'inertia/routing',
  },
  {
    id: 'inertia/no-raw-model-prop',
    overridable: true,
    stack: 'inertia',
    files: PHP,
    skip: (ctx) => ctx.isTest,
    gate: (gates) => gates.laravelDataObjects,
    custom: (lines, i) => {
      if (!/Inertia::render\s*\(|inertia\s*\(/.test(lines[i])) return false;
      // A bare variable or an Eloquent call as a prop value, rather than a Data object.
      return /=>\s*\$\w+\s*[,)]/.test(lines[i]) || /=>\s*\w+::(all|get|find|first)\s*\(/.test(lines[i]);
    },
    message:
      'Passing a model or collection straight into Inertia props ships every column to the browser, including ones added later. Wrap it in a Data object so the payload is declared.',
    doc: 'inertia/props',
  },
];
