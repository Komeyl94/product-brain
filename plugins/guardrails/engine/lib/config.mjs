/**
 * Repository-level configuration, and the policy that governs it.
 *
 * The default is deliberately severe: a product repository cannot switch a rule off.
 * That is the whole point of a central guardrail — if every repo can opt out, the
 * guardrail describes an aspiration rather than a standard, and the teams that most
 * need it are the ones most likely to opt out.
 *
 * What a repository *can* do is turn off a rule the maintainers have explicitly
 * marked `overridable` — the conventions, not the safety rules. Anything else needs a
 * change here, which is a pull request the maintainers review. That is the
 * exception process, and it is meant to be visible.
 */

import { join } from 'node:path';
import { readJson } from './detect.mjs';

export const CONFIG_FILENAME = '.guardrails.json';

/**
 * @returns {{rules: Record<string,'off'|'error'>, rejected: Array<{id: string, reason: string}>}}
 */
export function loadConfig(root, rules) {
  const raw = readJson(join(root, CONFIG_FILENAME));
  const result = { rules: {}, rejected: [] };
  if (!raw || typeof raw.rules !== 'object' || raw.rules === null) return result;

  const byId = new Map(rules.map((rule) => [rule.id, rule]));

  for (const [id, severity] of Object.entries(raw.rules)) {
    const rule = byId.get(id);
    if (!rule) {
      result.rejected.push({ id, reason: 'no such rule' });
      continue;
    }
    if (severity !== 'off') {
      result.rejected.push({ id, reason: `unsupported severity "${severity}"` });
      continue;
    }
    if (rule.waivable === false) {
      result.rejected.push({ id, reason: 'safety rule — cannot be disabled' });
      continue;
    }
    if (!rule.overridable) {
      result.rejected.push({
        id,
        reason: 'not overridable — open a PR against the Product Brain repo to request an exception',
      });
      continue;
    }
    result.rules[id] = 'off';
  }
  return result;
}
