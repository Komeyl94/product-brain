/**
 * Stack-agnostic rules.
 *
 * Everything here guards against something that is expensive or impossible to undo
 * once it reaches a shared branch — a leaked credential, a conflict marker that breaks
 * the pipeline for everyone. That is why these are the only rules in the whole set
 * declared `waivable: false`: an escape hatch on a credential check is the same as no
 * check, because the moment someone is in a hurry is exactly the moment they use it.
 */

const ANY_TEXT = () => true;

export const coreRules = [
  {
    id: 'core/no-conflict-marker',
    stack: 'core',
    files: ANY_TEXT,
    raw: true,
    waivable: false,
    test: /^(<{7}|={7}|>{7})(\s|$)/,
    message:
      'Unresolved merge-conflict marker. Resolve the conflict before writing the file — a marker that reaches a shared branch breaks the pipeline for everyone.',
    doc: 'core/conflict-markers',
  },
  {
    id: 'core/no-hardcoded-secret',
    stack: 'core',
    files: ANY_TEXT,
    waivable: false,
    skip: (ctx) => /\.(example|template|dist|md)$/.test(ctx.filePath) || /\.env\.example$/.test(ctx.filePath),
    // The name list is the whole rule: too narrow and a credential walks through, too
    // broad (a bare "token") and every csrf_token in the codebase is a violation.
    test: /(api[_-]?key|apikey|api[_-]?token|secret|password|passwd|auth[_-]?token|access[_-]?token|refresh[_-]?token|private[_-]?token|client[_-]?secret|bearer)\s*[:=]\s*['"`][A-Za-z0-9_\-./+=]{12,}['"`]/i,
    message:
      'Hardcoded credential. Read it from the environment and add the key to .env.example with an empty value.',
    doc: 'core/secrets',
  },
  {
    id: 'core/no-vendor-token',
    stack: 'core',
    files: ANY_TEXT,
    waivable: false,
    skip: (ctx) => /\.(example|template|dist)$/.test(ctx.filePath),
    // Recognisable token shapes, each with a fixed vendor prefix, so a match is a match.
    test: /\b(AKIA[0-9A-Z]{16}|glpat-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{36,}|xox[baprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9]{32,})\b/,
    message:
      'This looks like a real vendor credential (AWS, GitLab, GitHub, Slack or an API key). Remove it and rotate it — it is already in your shell history.',
    doc: 'core/secrets',
  },
  {
    id: 'core/no-private-key',
    stack: 'core',
    files: ANY_TEXT,
    raw: true,
    waivable: false,
    test: /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
    message:
      'Private key material must never be committed. Store it in the secret manager and inject it at runtime.',
    doc: 'core/secrets',
  },
];
