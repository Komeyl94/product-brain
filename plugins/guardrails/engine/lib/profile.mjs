/**
 * Per-repository profile: which stacks are present, and how far each has adopted the
 * patterns the rules would otherwise demand.
 *
 * The adoption counters exist to make the rules a *ratchet*. A rule that fires on every
 * file of a legacy codebase is noise that teams learn to waive; the same rule applied
 * only where the codebase has already committed to the new pattern is a rule that holds.
 * So `prefer-inject` stays silent in a repo that is 95% constructor-injected, and
 * `no-ngmodule` stays silent in a deliberately NgModule-based Angular 20 app.
 *
 * Scanning is capped and cached — a guardrail that makes every edit feel slow gets
 * switched off, which is a worse outcome than a guardrail that is occasionally stale.
 */

import { readFileSync, writeFileSync, mkdirSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { homedir, tmpdir } from 'node:os';
import { detectStacks, readJson, MANIFESTS, mtimeOf } from './detect.mjs';

const CACHE_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const SCAN_FILE_CAP = 6000;
const MAX_FILE_BYTES = 400_000;

const SKIP_DIRS = new Set([
  'node_modules', 'vendor', '.git', 'dist', 'build', 'coverage', 'tmp', 'storage',
  '.angular', '.nx', '.cache', '.vscode', '.idea', 'public', 'bootstrap', '.dart_tool',
  'ios', 'android', 'macos', 'windows', 'linux', '.phpstan-cache',
]);

const cacheDir = () => {
  try {
    return join(homedir(), '.cache', 'product-brain-guardrails');
  } catch {
    return join(tmpdir(), 'product-brain-guardrails');
  }
};

/**
 * Adoption probes, one per stack. Each sees a file's text and bumps counters.
 * Only counters that actually gate a rule belong here.
 */
const PROBES = {
  angular: {
    match: (f) => (f.endsWith('.ts') && !f.endsWith('.d.ts')) || f.endsWith('.html'),
    count(text, file, c) {
      if (file.endsWith('.ts')) {
        if (/@NgModule\s*\(/.test(text)) c.ngModule = (c.ngModule ?? 0) + 1;
        if (/standalone:\s*true/.test(text)) c.standalone = (c.standalone ?? 0) + 1;
        if (/=\s*inject\s*\(/.test(text)) c.inject = (c.inject ?? 0) + 1;
        if (hasConstructorParamProperties(text)) c.ctorDi = (c.ctorDi ?? 0) + 1;
      }
      if (/\*ngIf|\*ngFor|\*ngSwitch/.test(text)) c.structural = (c.structural ?? 0) + 1;
      if (/@if\s*\(|@for\s*\(|@switch\s*\(/.test(text)) c.controlFlow = (c.controlFlow ?? 0) + 1;
    },
  },
  php: {
    match: (f) => f.endsWith('.php'),
    count(text, file, c) {
      c.files = (c.files ?? 0) + 1;
      if (/^\s*declare\s*\(\s*strict_types\s*=\s*1\s*\)/m.test(text)) {
        c.strictTypes = (c.strictTypes ?? 0) + 1;
      }
      if (/\bfinal\s+(readonly\s+)?class\b/.test(text)) c.finalClass = (c.finalClass ?? 0) + 1;
      if (/^\s*class\s+\w/m.test(text)) c.classes = (c.classes ?? 0) + 1;
    },
  },
  laravel: {
    match: (f) => f.endsWith('.php'),
    count(text, file, c) {
      if (/[/\\]app[/\\]Actions[/\\]/.test(file)) c.actions = (c.actions ?? 0) + 1;
      if (/[/\\]app[/\\]Data[/\\]/.test(file)) c.dataObjects = (c.dataObjects ?? 0) + 1;
      if (/[/\\]app[/\\]Http[/\\]Controllers[/\\]/.test(file)) {
        c.controllers = (c.controllers ?? 0) + 1;
      }
    },
  },
  react: {
    match: (f) => /\.(tsx|jsx)$/.test(f),
    count(text, file, c) {
      c.files = (c.files ?? 0) + 1;
      if (/\bextends\s+(React\.)?(Pure)?Component\b/.test(text)) {
        c.classComponents = (c.classComponents ?? 0) + 1;
      }
    },
  },
  flutter: {
    match: (f) => f.endsWith('.dart'),
    count(text, file, c) {
      c.files = (c.files ?? 0) + 1;
      if (/\bconst\s+\w+\s*\(/.test(text)) c.constCtors = (c.constCtors ?? 0) + 1;
    },
  },
};

/**
 * True when a class constructor declares parameter properties (`private x: T`).
 * Scans balanced parens rather than regex-matching, so multi-line constructors and
 * `@Inject(TOKEN) private x: T` are both handled correctly.
 */
export function hasConstructorParamProperties(text) {
  const PARAM_PROP = /\b(private|public|protected)\s+(readonly\s+)?\w+\s*[?!]?\s*:/;
  let from = 0;
  for (;;) {
    const start = text.indexOf('constructor', from);
    if (start === -1) return false;
    let i = start + 'constructor'.length;
    while (i < text.length && /\s/.test(text[i])) i++;
    if (text[i] !== '(') {
      from = start + 1;
      continue;
    }
    const open = i;
    let depth = 0;
    for (; i < text.length; i++) {
      if (text[i] === '(') depth++;
      else if (text[i] === ')') {
        depth--;
        if (depth === 0) break;
      }
    }
    if (PARAM_PROP.test(text.slice(open + 1, i))) return true;
    from = i + 1;
  }
}

function scan(root, stacks) {
  const probes = [...stacks].map((s) => PROBES[s]).filter(Boolean);
  const active = [...stacks].filter((s) => PROBES[s]);
  const adoption = Object.fromEntries(active.map((s) => [s, {}]));
  if (!probes.length) return adoption;

  let seen = 0;
  const stack = [root];
  while (stack.length && seen < SCAN_FILE_CAP) {
    const dir = stack.pop();
    let entries;
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      if (seen >= SCAN_FILE_CAP) break;
      const full = join(dir, entry.name);
      if (entry.isDirectory()) {
        if (!SKIP_DIRS.has(entry.name) && !entry.name.startsWith('.')) stack.push(full);
        continue;
      }
      const interested = active.filter((s) => PROBES[s].match(entry.name));
      if (!interested.length) continue;
      let text;
      try {
        if (statSync(full).size > MAX_FILE_BYTES) continue;
        text = readFileSync(full, 'utf8');
      } catch {
        continue;
      }
      seen++;
      for (const s of interested) PROBES[s].count(text, full, adoption[s]);
    }
  }
  return adoption;
}

/**
 * Ratchet gates derived from adoption. Each answers "has this codebase committed to
 * the pattern strongly enough that a new violation is a regression rather than a
 * continuation of how it already works?"
 */
function buildGates({ stacks, versions, adoption }) {
  const gates = {};
  const ng = adoption.angular ?? {};
  const php = adoption.php ?? {};
  const laravel = adoption.laravel ?? {};

  if (stacks.has('angular')) {
    const major = versions.angular ?? 0;
    gates.angularStandalone = ng.standalone > (ng.ngModule ?? 0) * 2 || (major >= 19 && !ng.ngModule);
    gates.angularControlFlow = major >= 17 && ((ng.controlFlow ?? 0) >= 3 || !ng.structural);
    gates.angularInject =
      major >= 16 &&
      (((ng.inject ?? 0) >= 5 && (ng.inject ?? 0) >= (ng.ctorDi ?? 0) * 0.4) ||
        (major >= 19 && (ng.inject ?? 0) >= (ng.ctorDi ?? 0) * 0.15));
  }

  if (stacks.has('php')) {
    // Only demand strict_types where most of the codebase already declares it; adding it
    // to one new file in a repo that has none changes behaviour inconsistently.
    gates.phpStrictTypes = (php.strictTypes ?? 0) >= Math.max(5, (php.files ?? 0) * 0.6);
    gates.phpFinalClasses = (php.finalClass ?? 0) >= Math.max(5, (php.classes ?? 0) * 0.4);
  }

  if (stacks.has('laravel')) {
    // "Controllers delegate to Actions" only makes sense once an Actions layer exists.
    gates.laravelActions = (laravel.actions ?? 0) >= 3;
    gates.laravelDataObjects = (laravel.dataObjects ?? 0) >= 3;
  }

  return gates;
}

export function buildProfile(root) {
  const { stacks, versions } = detectStacks(root);
  const adoption = scan(root, stacks);
  // `stacks` is a Set everywhere in memory; the cache boundary is the only place it is
  // ever an array, and converting anywhere else gives the same function two return shapes.
  const profile = {
    root,
    stacks,
    versions,
    adoption,
    builtAt: Date.now(),
    manifestMtimes: Object.fromEntries(MANIFESTS.map((m) => [m, mtimeOf(join(root, m))])),
  };
  profile.gates = buildGates({ stacks, versions, adoption });
  return profile;
}

/** Cached profile. A stale profile is acceptable; a slow edit is not. */
export function getProfile(root, { noCache = false } = {}) {
  const key = createHash('sha1').update(root).digest('hex').slice(0, 16);
  const path = join(cacheDir(), `${key}.json`);
  const mtimes = Object.fromEntries(MANIFESTS.map((m) => [m, mtimeOf(join(root, m))]));

  if (!noCache) {
    const cached = readJson(path);
    if (
      cached &&
      Date.now() - cached.builtAt < CACHE_TTL_MS &&
      MANIFESTS.every((m) => cached.manifestMtimes?.[m] === mtimes[m])
    ) {
      cached.stacks = new Set(cached.stacks);
      return cached;
    }
  }

  const profile = buildProfile(root);
  try {
    mkdirSync(cacheDir(), { recursive: true });
    writeFileSync(path, JSON.stringify({ ...profile, stacks: [...profile.stacks] }, null, 2));
  } catch {
    /* cache is best-effort */
  }
  return profile;
}
