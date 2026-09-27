/**
 * React rules.
 *
 * The hook-ordering and exhaustive-deps classes are left to eslint-plugin-react-hooks,
 * which has a real parser and gets them right. What is here is the set a linter tends
 * to be configured to warn about rather than fail on, and which is cheap to catch at
 * write time.
 */

const JSX = /\.(tsx|jsx)$/;

export const reactRules = [
  {
    id: 'react/no-dangerously-set-inner-html',
    stack: 'react',
    files: JSX,
    test: /dangerouslySetInnerHTML/,
    message:
      'dangerouslySetInnerHTML injects unescaped HTML — an XSS surface. Render the value as text, or sanitize it with a vetted sanitizer first.',
    doc: 'react/security',
  },
  {
    id: 'react/no-array-index-key',
    overridable: true,
    stack: 'react',
    files: JSX,
    test: /key\s*=\s*\{\s*(i|idx|index)\s*\}/,
    message:
      'An array index as key makes React reuse the wrong element when the list reorders, carrying stale state with it. Use a stable id from the data.',
    doc: 'react/rendering',
  },
  {
    id: 'react/no-class-component',
    stack: 'react',
    files: JSX,
    gate: (_gates, ctx) => (ctx.profile.adoption?.react?.classComponents ?? 0) === 0,
    test: /\bextends\s+(React\.)?(Pure)?Component\b/,
    message:
      'This project has no class components. Write a function component with hooks.',
    doc: 'react/components',
  },
];
