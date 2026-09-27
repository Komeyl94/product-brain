import { coreRules } from './core.mjs';
import { phpRules } from './php.mjs';
import { laravelRules } from './laravel.mjs';
import { symfonyRules } from './symfony.mjs';
import { typescriptRules } from './typescript.mjs';
import { reactRules } from './react.mjs';
import { inertiaRules } from './inertia.mjs';
import { angularRules } from './angular.mjs';
import { flutterRules } from './flutter.mjs';

export const RULE_SETS = {
  core: coreRules,
  php: phpRules,
  laravel: laravelRules,
  symfony: symfonyRules,
  typescript: typescriptRules,
  react: reactRules,
  inertia: inertiaRules,
  angular: angularRules,
  flutter: flutterRules,
};

export const ALL_RULES = Object.values(RULE_SETS).flat();

/**
 * Rules for the stacks actually present. Filtering here rather than inside the runner
 * keeps a Flutter repository from paying for the PHP rule set on every write.
 */
export function rulesFor(stacks) {
  return Object.entries(RULE_SETS)
    .filter(([stack]) => stacks.has(stack))
    .flatMap(([, rules]) => rules);
}

/** Fails fast on a duplicated id — two rules sharing one id would silently shadow. */
export function assertUniqueIds(rules = ALL_RULES) {
  const seen = new Set();
  for (const rule of rules) {
    if (seen.has(rule.id)) throw new Error(`Duplicate guardrail rule id: ${rule.id}`);
    seen.add(rule.id);
  }
  return true;
}
