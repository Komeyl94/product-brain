/**
 * Unified-diff parsing.
 *
 * The CI gate and the pre-commit check inspect added lines only, exactly as the hook
 * inspects only the content about to be written. Without this, switching the guardrail
 * on in an existing repository would fail every pipeline until the whole codebase was
 * rewritten, and the guardrail would be switched back off the same afternoon.
 */

import { execFileSync } from 'node:child_process';

const HUNK = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/;

/**
 * Contiguous runs of added lines, with the line number each run starts at in the new
 * file. Runs are kept separate rather than concatenated so that window-based rules
 * (an `await` six lines above a `context` use) cannot match across a gap that does not
 * exist in the real file.
 *
 * @returns {Map<string, Array<{content: string, baseLine: number}>>} added blocks by path
 */
export function parseUnifiedDiff(diffText) {
  const byFile = new Map();
  let path = null;
  let block = null;
  let newLine = 0;

  const flush = () => {
    if (path && block?.lines.length) {
      if (!byFile.has(path)) byFile.set(path, []);
      byFile.get(path).push({ content: block.lines.join('\n'), baseLine: block.start - 1 });
    }
    block = null;
  };

  for (const line of diffText.split('\n')) {
    if (line.startsWith('diff --git ')) {
      flush();
      path = null;
      continue;
    }
    if (line.startsWith('+++ ')) {
      flush();
      const target = line.slice(4).trim();
      path = target === '/dev/null' ? null : target.replace(/^b\//, '');
      continue;
    }

    const hunk = HUNK.exec(line);
    if (hunk) {
      flush();
      newLine = Number.parseInt(hunk[1], 10);
      continue;
    }

    if (!path) continue;
    if (line.startsWith('---') || line.startsWith('index ') || line.startsWith('\\')) continue;

    if (line.startsWith('+')) {
      if (!block) block = { start: newLine, lines: [] };
      block.lines.push(line.slice(1));
      newLine++;
    } else if (line.startsWith('-')) {
      flush(); // a removal ends the current run; it does not advance the new-file line
    } else if (line.startsWith(' ')) {
      flush();
      newLine++;
    }
  }
  flush();
  return byFile;
}

export function gitDiff(args, cwd) {
  return execFileSync('git', ['diff', '-U0', '--no-color', '--no-ext-diff', ...args], {
    cwd,
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  });
}

/** Merge base against a target branch, so a long-lived branch is judged on its own work. */
export function mergeBase(ref, cwd) {
  try {
    return execFileSync('git', ['merge-base', 'HEAD', ref], { cwd, encoding: 'utf8' }).trim();
  } catch {
    return null;
  }
}
