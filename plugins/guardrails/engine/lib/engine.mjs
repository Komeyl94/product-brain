/**
 * The rule runner.
 *
 * Every entry point — the Claude PreToolUse hook, a pre-commit check and the
 * CI gate — funnels through `checkBlock` with the same rule set. That is the property
 * that matters: a rule cannot be strict for the agent and lax for the human, because
 * there is only one implementation of it.
 *
 * Rules are always applied to *added* content only. The hook sees what Claude is about
 * to write; the pre-commit and CI entry points see added diff lines. Existing code is never
 * scanned, so adopting the guardrails does not require fixing a legacy codebase first.
 */

const COMMENT_STYLES = {
  '.php': { line: /(^|[^:"'`])(\/\/|#(?!\[)).*$/, block: true },
  '.ts': { line: /(^|[^:"'`])\/\/.*$/, block: true },
  '.tsx': { line: /(^|[^:"'`])\/\/.*$/, block: true },
  '.js': { line: /(^|[^:"'`])\/\/.*$/, block: true },
  '.jsx': { line: /(^|[^:"'`])\/\/.*$/, block: true },
  '.mjs': { line: /(^|[^:"'`])\/\/.*$/, block: true },
  '.dart': { line: /(^|[^:"'`])\/\/.*$/, block: true },
  '.html': { line: null, block: false },
};

const extOf = (path) => {
  const match = String(path).match(/(\.[a-z0-9]+)$/i);
  return match ? match[1].toLowerCase() : '';
};

const TEST_PATH =
  /(^|[/\\])(tests?|spec|__tests__)[/\\]|\.(spec|test|check)\.[jt]sx?$|Test\.php$|_test\.dart$/i;

/** Strip comments so a rule cannot fire on prose that merely mentions the pattern. */
function decomment(line, ext) {
  const style = COMMENT_STYLES[ext];
  if (!style) return line;
  let out = line;
  if (style.line) out = out.replace(style.line, '$1');
  if (style.block && /^\s*(\*|\/\*)/.test(line)) out = '';
  return out;
}

export function buildContext({ filePath, profile, relPath }) {
  const ext = extOf(filePath);
  return {
    filePath,
    relPath: relPath ?? filePath,
    ext,
    isTest: TEST_PATH.test(filePath),
    isHtml: ext === '.html',
    profile,
    stacks: profile.stacks,
    gates: profile.gates ?? {},
    versions: profile.versions ?? {},
  };
}

function applies(rule, ctx, config) {
  if ((config.rules?.[rule.id] ?? rule.severity ?? 'error') === 'off') return false;
  if (!ctx.stacks.has(rule.stack)) return false;
  if (typeof rule.files === 'function' ? !rule.files(ctx.filePath, ctx) : !rule.files.test(ctx.filePath)) {
    return false;
  }
  if (rule.skip?.(ctx)) return false;
  if (rule.gate && !rule.gate(ctx.gates, ctx)) return false;
  return true;
}

/**
 * A waiver marks a line the author has deliberately exempted. Rules declared
 * `waivable: false` — secrets, conflict markers — ignore it: a rule that protects the
 * repository from something unrecoverable must not have an opt-out that a hurried
 * commit can reach for.
 */
const waived = (rawLines, index) =>
  /guardrail:allow/.test(rawLines[index] ?? '') ||
  (index > 0 && /guardrail:allow/.test(rawLines[index - 1] ?? ''));

/**
 * Run every applicable rule over one block of added content.
 *
 * @returns {Array<{rule, line: number|null, snippet: string|null, waivable: boolean}>}
 */
export function checkBlock({ content, filePath, profile, rules, config = {}, baseLine = null, relPath, firstOnly = true }) {
  if (!content) return [];
  const ctx = buildContext({ filePath, profile, relPath });

  const rawLines = content.split('\n');
  const fileDisabled = /guardrail:disable-file/.test(content);
  const lines = ctx.isHtml ? rawLines : rawLines.map((l) => decomment(l, ctx.ext));
  const findings = [];

  for (const rule of rules) {
    if (!applies(rule, ctx, config)) continue;
    const waivable = rule.waivable !== false;
    if (fileDisabled && waivable) continue;

    if (rule.wholeCustom) {
      if (rule.wholeCustom(lines.join('\n'), ctx) && !(waivable && /guardrail:allow/.test(content))) {
        findings.push({ rule, line: null, snippet: null, waivable });
      }
      continue;
    }

    const source = rule.raw ? rawLines : lines;
    for (let i = 0; i < source.length; i++) {
      const hit = rule.custom ? rule.custom(source, i, ctx) : rule.test.test(source[i]);
      if (!hit) continue;
      if (waivable && waived(rawLines, i)) continue;
      findings.push({
        rule,
        line: baseLine == null ? null : baseLine + i + 1,
        snippet: rawLines[i].trim().slice(0, 140),
        waivable,
      });
      if (firstOnly) break;
    }
  }
  return findings;
}

/** Collapse to one finding per rule, keeping the first — feedback stays actionable. */
export function dedupeByRule(findings) {
  const seen = new Map();
  for (const finding of findings) {
    if (!seen.has(finding.rule.id)) seen.set(finding.rule.id, finding);
  }
  return [...seen.values()];
}
