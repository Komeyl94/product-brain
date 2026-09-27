/**
 * Finding output.
 *
 * The hook format is written for a model: the message says what is wrong and what to
 * do instead, because a block that does not say how to proceed just produces a retry
 * of the same code. The CI format is written for a person reading a job log.
 */

const DOC_BASE = 'guardrails';

const location = (finding, relPath) => (finding.line ? `${relPath}:${finding.line}` : relPath);

/** Blocking message handed back to Claude on a PreToolUse denial. */
export function formatForHook(findings, { relPath, stacks }) {
  const lines = [
    `Guardrail blocked this write to ${relPath}`,
    `(stacks: ${[...stacks].filter((s) => s !== 'core').join(', ') || 'core'})`,
    '',
  ];

  for (const finding of findings) {
    lines.push(`  ✗ [${finding.rule.id}] ${location(finding, relPath)}`);
    if (finding.snippet) lines.push(`      ${finding.snippet}`);
    lines.push(`      → ${finding.rule.message}`);
    if (finding.rule.doc) lines.push(`      see: ${DOC_BASE}/${finding.rule.doc}`);
    lines.push('');
  }

  const waivable = findings.filter((f) => f.waivable);
  if (waivable.length) {
    lines.push(
      'Fix these and retry. If a violation is genuinely correct here, append `guardrail:allow`',
      'to the line and say why in your reply to the user — an unexplained waiver is a defect.',
    );
  } else {
    lines.push(
      'These rules cannot be waived. Fix the code — there is no escape hatch for credentials',
      'or conflict markers, by design.',
    );
  }
  return lines.join('\n');
}

/** Job-log output for the CI gate and the local pre-commit check. */
export function formatForCli(byFile, { rejected = [] } = {}) {
  const lines = [];
  let total = 0;

  for (const [relPath, findings] of byFile) {
    if (!findings.length) continue;
    lines.push(`\n  ${relPath}`);
    for (const finding of findings) {
      total++;
      const where = finding.line ? `:${finding.line}` : '';
      lines.push(`    ✗ ${finding.rule.id}${where}`);
      if (finding.snippet) lines.push(`        ${finding.snippet}`);
      lines.push(`      ${finding.rule.message}`);
    }
  }

  if (rejected.length) {
    lines.push('', '  .guardrails.json entries ignored:');
    for (const entry of rejected) lines.push(`    • ${entry.id} — ${entry.reason}`);
  }

  if (!total) {
    lines.push('  No guardrail violations in the changed lines.');
    return { text: lines.join('\n'), total };
  }

  lines.unshift(
    '',
    '  ┌─────────────────────────────────────────────────────────────┐',
    '  │                  GUARDRAIL VIOLATIONS                        │',
    '  └─────────────────────────────────────────────────────────────┘',
  );
  lines.push(
    '',
    `  ${total} violation${total === 1 ? '' : 's'} in added lines.`,
    '  Only lines this change adds are checked — existing code is never scanned.',
    '',
  );
  return { text: lines.join('\n'), total };
}
