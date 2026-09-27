#!/usr/bin/env bash
# SessionStart hook: warn when a program Product Brain needs is missing. Plain shell on purpose, so
# it still runs when Python is the thing that's missing. Silent when everything is there; never
# fails a session. Also runnable by hand: bash hooks/check-deps.sh

case "$(uname -s 2>/dev/null)" in
  Darwin) os=mac ;;
  MINGW*|MSYS*|CYGWIN*) os=windows ;;
  *) os=linux ;;
esac

hint() {  # hint <mac> <linux> <windows>
  case "$os" in mac) echo "$1" ;; linux) echo "$2" ;; windows) echo "$3" ;; esac
}

missing=""
need() {  # need <program> <why> <install hint>
  command -v "$1" >/dev/null 2>&1 && return
  missing="$missing
  - $1 ($2). Install: $3"
}

need git "pulls the hub and app repos" \
  "$(hint 'xcode-select --install (or brew install git)' 'sudo apt install git' 'winget install Git.Git')"

# python3 must actually run: on Windows the name can be a Microsoft Store stub that only opens the Store.
if ! python3 -c "" >/dev/null 2>&1; then
  if [ "$os" = windows ] && python -c "" >/dev/null 2>&1; then
    missing="$missing
  - python3 (runs pb and the Product Brain hooks). Python is installed as \`python\` only, or \`python3\` is the Microsoft Store stub. Turn off the python entries under Settings > Apps > Advanced app settings > App execution aliases, then reinstall Python from python.org with \"Add python.exe to PATH\" ticked."
  else
    missing="$missing
  - python3 (runs pb and the Product Brain hooks). Install: $(hint 'brew install python' 'sudo apt install python3' 'python.org installer, tick "Add python.exe to PATH"')"
  fi
fi

need node "runs the guardrails checks" \
  "$(hint 'brew install node' 'sudo apt install nodejs' 'winget install OpenJS.NodeJS.LTS')"

hub="${CLAUDE_PROJECT_DIR:-.}"
if [ -f "$hub/brain.config.json" ]; then
  need graphify "builds the hub's knowledge graph" \
    "pipx install graphifyy (or: python3 -m pip install --user graphifyy)"
  # Every tool connection the hub declares in .mcp.json needs its program.
  if [ -f "$hub/.mcp.json" ]; then
    for cmd in $(sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$hub/.mcp.json" | sort -u); do
      case "$cmd" in
        glab) need glab "the GitLab connection" "$(hint 'brew install glab' 'see https://gitlab.com/gitlab-org/cli#installation' 'winget install GLab.GLab')" ;;
        gh)   need gh "the GitHub connection" "$(hint 'brew install gh' 'see https://github.com/cli/cli#installation' 'winget install GitHub.cli')" ;;
        uvx)  need uvx "the Jira connection, comes with uv" "$(hint 'brew install uv' 'curl -LsSf https://astral.sh/uv/install.sh | sh' 'winget install astral-sh.uv')" ;;
        *)    need "$cmd" "a tool connection in .mcp.json" "see the hub README" ;;
      esac
    done
  fi
fi

if [ -n "$missing" ]; then
  echo "Product Brain: these programs are missing on this computer ($os):$missing
Tell the user once, early, in plain words: what each one is for and the install command for their
system. Offer to run the install for them, and ask first. Then have them restart Claude Code."
fi
exit 0
