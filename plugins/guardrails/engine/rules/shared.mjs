/**
 * Helpers shared between rule sets.
 */

/**
 * The first argument of a call, stopping at the first comma outside a string.
 *
 * Raw-SQL rules need this: `orderByRaw('col ilike ?', ["{$value}%"])` is *correct*
 * code — the variable is in the bindings array, which is exactly where it belongs.
 * Scanning the whole line flags it, so the rule must see only the SQL string.
 */
export function firstArgument(text) {
  let quote = null;
  let depth = 0;
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (quote) {
      if (char === '\\') i++;
      else if (char === quote) quote = null;
      continue;
    }
    if (char === '"' || char === "'" || char === '`') quote = char;
    else if (char === '(' || char === '[') depth++;
    else if (char === ')' || char === ']') {
      if (depth === 0) return text.slice(0, i);
      depth--;
    } else if (char === ',' && depth === 0) return text.slice(0, i);
  }
  return text;
}

/**
 * True when a variable reaches a SQL string by interpolation or concatenation.
 *
 * `$` is only interpolation in PHP when followed by an identifier or `{` — the `$` in
 * `"payment_terms !~ '^[0-9]+$'"` is a regex anchor, and flagging it teaches people
 * that the rule cries wolf.
 */
export function hasInterpolatedSql(line, callPattern) {
  const match = callPattern.exec(line);
  if (!match) return false;
  const argument = firstArgument(line.slice(match.index + match[0].length));
  return (
    /"[^"]*\$[a-zA-Z_{]/.test(argument) ||
    /['"]\s*\.\s*\$/.test(argument) ||
    /\$\w+\s*\.\s*['"]/.test(argument)
  );
}
