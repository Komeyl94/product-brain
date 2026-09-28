#!/usr/bin/env node
/**
 * Guardrail CLI — one rule set, three enforcement surfaces.
 *
 *   guardrail hook            PreToolUse: blocks Claude's write before it lands
 *   guardrail staged          pre-commit: judges staged changes
 *   guardrail range <ref>     CI / pre-push: blocks the merge request
 *   guardrail files <paths>   ad-hoc, whole-file check
 *   guardrail info            what was detected here, and which gates are open
 *
 * `hook` never blocks on an internal error. A guardrail that breaks the agent when the
 * guardrail itself has a bug is worse than no guardrail, because the failure looks like
 * the agent's fault and the whole system loses trust.
 */

import { readFileSync, existsSync } from 'node:fs';
import { resolve, relative, dirname, sep } from 'node:path';
import process from 'node:process';

import { findRepoRoot } from './lib/detect.mjs';
import { getProfile } from './lib/profile.mjs';
import { checkBlock, dedupeByRule } from './lib/engine.mjs';
import { loadConfig } from './lib/config.mjs';
import { formatForHook, formatForCli } from './lib/report.mjs';
import { parseUnifiedDiff, gitDiff, mergeBase } from './lib/diff.mjs';
import { rulesFor, assertUniqueIds, ALL_RULES } from './rules/index.mjs';

const SKIP_PATH = /[/\\](node_modules|vendor|dist|build|coverage|\.git)[/\\]/;

function contextFor(root) {
  const profile = getProfile(root);
  const rules = rulesFor(profile.stacks);
  // Validated against every rule, not just the active ones: an entry for a stack this
  // repo does not have is a stale config line, not an unknown rule, and saying so is
  // the difference between a useful warning and a confusing one.
  const config = loadConfig(root, ALL_RULES);
  return { profile, rules, config };
}

/* --------------------------------------------------------------------- hook */

function readStdin() {
  try {
    return readFileSync(0, 'utf8');
  } catch {
    return '';
  }
}

/** Every block of content the tool call would introduce, with a line offset when derivable. */
function blocksFromToolInput(tool, input) {
  const blocks = [];
  let existing = null;
  try {
    existing = readFileSync(input.file_path, 'utf8');
  } catch {
    /* new file */
  }

  const offsetOf = (needle) => {
    if (existing == null || !needle) return null;
    const index = existing.indexOf(needle);
    return index === -1 ? null : existing.slice(0, index).split('\n').length - 1;
  };

  if (tool === 'Write') {
    blocks.push({ content: input.content ?? '', baseLine: 0 });
  } else if (tool === 'Edit') {
    blocks.push({ content: input.new_string ?? '', baseLine: offsetOf(input.old_string) });
  } else {
    for (const edit of input.edits ?? []) {
      blocks.push({ content: edit.new_string ?? '', baseLine: offsetOf(edit.old_string) });
    }
  }
  return blocks;
}

function runHook() {
  const payload = JSON.parse(readStdin() || '{}');
  const tool = payload.tool_name;
  if (!['Edit', 'Write', 'MultiEdit'].includes(tool)) return 0;

  const input = payload.tool_input ?? {};
  const filePath = input.file_path;
  if (!filePath || SKIP_PATH.test(filePath)) return 0;

  const root = findRepoRoot(dirname(resolve(filePath)));
  if (!root) return 0;

  const { profile, rules, config } = contextFor(root);
  if (!rules.length) return 0;

  const relPath = resolve(filePath).startsWith(root)
    ? resolve(filePath).slice(root.length + 1)
    : filePath;

  const findings = [];
  for (const block of blocksFromToolInput(tool, input)) {
    findings.push(
      ...checkBlock({ ...block, filePath, relPath, profile, rules, config: config.rules }),
    );
  }

  const unique = dedupeByRule(findings);
  if (!unique.length) return 0;

  process.stderr.write(formatForHook(unique, { relPath, stacks: profile.stacks }) + '\n');
  return 2;
}

/* ---------------------------------------------------------------------- cli */

function checkDiff(root, diffText) {
  const { profile, rules, config } = contextFor(root);
  const byFile = new Map();

  for (const [relPath, blocks] of parseUnifiedDiff(diffText)) {
    if (SKIP_PATH.test(`${sep}${relPath}`)) continue;
    const filePath = resolve(root, relPath);
    const findings = [];
    for (const block of blocks) {
      findings.push(
        ...checkBlock({
          ...block,
          filePath,
          relPath,
          profile,
          rules,
          config: config.rules,
          firstOnly: false,
        }),
      );
    }
    if (findings.length) byFile.set(relPath, findings);
  }
  return { byFile, config, profile };
}

function report({ byFile, config }) {
  const { text, total } = formatForCli(byFile, { rejected: config.rejected });
  process.stdout.write(text + '\n');
  return total ? 1 : 0;
}

function runStaged(root) {
  return report(checkDiff(root, gitDiff(['--cached'], root)));
}

function runRange(root, ref) {
  const base = mergeBase(ref, root) ?? ref;
  return report(checkDiff(root, gitDiff([`${base}...HEAD`], root)));
}

function runFiles(root, paths) {
  const { profile, rules, config } = contextFor(root);
  const byFile = new Map();

  for (const path of paths) {
    const filePath = resolve(path);
    if (!existsSync(filePath) || SKIP_PATH.test(filePath)) continue;
    const relPath = filePath.startsWith(root) ? filePath.slice(root.length + 1) : filePath;
    const findings = checkBlock({
      content: readFileSync(filePath, 'utf8'),
      baseLine: 0,
      filePath,
      relPath,
      profile,
      rules,
      config: config.rules,
      firstOnly: false,
    });
    if (findings.length) byFile.set(relPath, findings);
  }
  return report({ byFile, config });
}

function runInfo(root) {
  const { profile, rules, config } = contextFor(root);
  const gates = Object.entries(profile.gates ?? {});
  const lines = [
    `repository : ${root}`,
    `stacks     : ${[...profile.stacks].join(', ')}`,
    `versions   : ${Object.entries(profile.versions).map(([k, v]) => `${k}@${v}`).join(', ') || '—'}`,
    `rules      : ${rules.length} active of ${ALL_RULES.length} total`,
    'gates      :',
    ...(gates.length
      ? gates.map(([name, open]) => `  ${open ? '✓' : '·'} ${name}`)
      : ['  —']),
  ];
  if (config.rejected.length) {
    lines.push('.guardrails.json entries ignored:');
    for (const entry of config.rejected) lines.push(`  • ${entry.id} — ${entry.reason}`);
  }
  process.stdout.write(lines.join('\n') + '\n');
  return 0;
}

/* --------------------------------------------------------------------- main */

function main(argv) {
  assertUniqueIds();
  const [command, ...rest] = argv;

  if (command === 'hook') return runHook();

  const root = findRepoRoot(process.cwd());
  if (!root) {
    process.stderr.write('guardrail: not inside a repository\n');
    return 0;
  }

  switch (command) {
    case 'staged':
      return runStaged(root);
    case 'range':
      return runRange(root, rest[0] ?? 'origin/develop');
    case 'files':
      return runFiles(root, rest);
    case 'info':
      return runInfo(root);
    default:
      process.stderr.write('usage: guardrail <hook|staged|range <ref>|files <paths…>|info>\n');
      return 64;
  }
}

const isHookMode = process.argv[2] === 'hook';
try {
  process.exitCode = main(process.argv.slice(2));
} catch (error) {
  if (isHookMode) {
    process.exitCode = 0; // never break the agent because the guardrail is broken
  } else {
    process.stderr.write(`guardrail: ${error.message}\n`);
    process.exitCode = 1;
  }
}
