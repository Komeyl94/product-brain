/**
 * TypeScript rules, shared by the Angular and React/Inertia stacks.
 */

const TS = /\.(ts|tsx)$/;
const TS_OR_JS = /\.(ts|tsx|js|jsx|mjs|cjs)$/;

export const typescriptRules = [
  {
    id: 'ts/no-any',
    stack: 'typescript',
    files: TS,
    skip: (ctx) => ctx.isTest || /\.d\.ts$/.test(ctx.filePath),
    test: /(:\s*any\b|\bas\s+any\b|<any>|\bany\[\]|Array<any>)/,
    message:
      '`any` switches off type checking for everything downstream of it. Use the real type, a generic, or `unknown` with narrowing.',
    doc: 'typescript/types',
  },
  {
    id: 'ts/no-ts-ignore',
    stack: 'typescript',
    files: TS,
    raw: true,
    test: /@ts-(ignore|nocheck)/,
    message:
      'Do not silence the compiler. Fix the type, or use `@ts-expect-error` with a comment saying why — it fails the build once the underlying problem is gone.',
    doc: 'typescript/types',
  },
  {
    id: 'ts/no-console',
    stack: 'typescript',
    files: TS_OR_JS,
    skip: (ctx) => ctx.isTest,
    test: /\bconsole\.(log|debug|info|trace)\s*\(/,
    message:
      'Leftover console logging reaches the browser in production. Remove it, or route it through the application logger.',
    doc: 'typescript/debugging',
  },
];
