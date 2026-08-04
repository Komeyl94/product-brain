# 🧠 Product Brain

> **One source of truth for product knowledge — across every repo, for every role, in whatever method your team already uses.**

Product Brain is an open framework for keeping product knowledge — specs, vocabulary, domains, decisions, meeting notes — in one place, connected to your code, and answerable by Claude. It works across multiple repositories, and it's **method-agnostic**: bring your own way of writing specs.

---

## The idea in one picture

```
                 ┌────────────────────────────────────┐
                 │            your hub repo            │   ← single source of truth
                 │  constitution · vocabulary · domains │
                 │  docs/ (specs, decisions, notes, …) │
                 │  graph/ (built over docs + code)    │
                 └───────────────┬────────────────────┘
                         pb sync  │  pulls code, builds one graph
                 ┌───────────────┴───────────────┐
                 ▼                                 ▼
          ┌─────────────┐                  ┌──────────────┐
          │   web-app   │                  │  backend-api │   ← your code repos
          │ (untouched) │                  │  (untouched) │      (nothing added)
          └─────────────┘                  └──────────────┘
```

The **hub** is its own git repo. Your application repos stay exactly as they are — the hub pulls them and builds a single knowledge graph over your docs *and* your code. Ask Claude anything; answers are grounded in real code and real decisions.

---

## Two things, kept separate

| **Product Brain (this framework)** | **Your hub (an instance)** |
|---|---|
| The `brainify` skill + templates + docs | Your team's actual knowledge |
| Tooling | Knowledge only — no skills inside |
| Lives here | Its own git repo, created by running `brainify` |

This separation is what keeps the framework method-neutral and your hub clean.

---

## What problems it solves

| # | Problem | Without Product Brain |
|---|---|---|
| 1 | Codebase questions | Read every file, ask the "code person" |
| 2 | Missing context | Code exists; nobody wrote down why |
| 3 | Vocabulary mismatch | "Session" in the meeting, `Appointment` in the code |
| 4 | Multi-repo knowledge | A question spans two repos and takes days |
| 5 | Institutional knowledge | Lives in people's heads, leaves when they do |

> Precise cross-repo *impact analysis* ("change X here → exactly these files break there") is **not** solved yet — it's a tracked [open problem](docs/multi-repo-architecture.md#13-open-problems-deferred-not-solved-here).

---

## What's in this repo

```
product-brain/
  README.md                         ← you are here
  CLAUDE.md                         ← framework guidance for Claude
  .claude-plugin/                   ← makes this repo a Claude Code plugin + marketplace
    plugin.json                     one-command install of the skill + pb CLI
    marketplace.json
  docs/
    getting-started.md              ← no-jargon guide for everyone
    multi-repo-architecture.md      ← the full architecture proposal
  skills/
    brainify/SKILL.md               ← the setup & maintenance skill
  bin/
    pb                              the hub CLI (on PATH automatically via the plugin)
    package-skill.sh                build the Cowork upload bundle on demand
    install-skill.sh                fallback installer (when you can't use plugins)
  templates/                        ← what a hub is made of (method-agnostic)
    brain.config.template.json
    constitution-template.md
    vocabulary-template.md
    domains-template.md
    spec-template.md
    doc-types/                      meeting-note, decision (ADR)
    workflows/                      pm, backend, frontend, qa, onboarding
    hub-claude-md-snippet.md        for a hub's CLAUDE.md
    app-repo-claude-md-snippet.md   optional: makes an app repo hub-aware
  examples/
    todo-app/                       ← a complete tiny hub (todo-api + todo-web)
  website/
    product-brain.html              ← documentation site (open in a browser)
```

---

## Quick start

### 1. Install the plugin (Claude Code)

Product Brain ships as a **Claude Code plugin**. Installing it adds the `brainify` skill *and* puts
the `pb` CLI on your `PATH` — **no scripts, no PATH editing, no manual copying**. In Claude Code:

```text
/plugin marketplace add Whotan/product-brain
/plugin install product-brain@product-hub
/reload-plugins
```

That's the entire install. (`graphify`, the local graph builder, is installed for you the first time
you set up a hub — see step 2.)

> **Using Cowork instead of Claude Code?** Plugins are a Claude Code feature. For Cowork, add the
> skill to your claude.ai account once: run `bin/package-skill.sh` to build `dist/brainify.skill`,
> then upload it at **claude.ai → Settings → Features**. After that, "set up product brain" works in
> any Cowork chat. (There's no supported way to auto-install a skill mid-session, so this one-time
> account step is required.)
>
> **Can't use plugins at all?** `bin/install-skill.sh` is a fallback that copies the skill into
> `~/.claude/skills` and optionally symlinks `pb`.

### 2. Create your hub — just ask

Open Claude in a new folder for your hub and say:

> **"Set up product brain"**

`brainify` does the technical parts **for you**: it installs `graphify` if it's missing, creates the
hub, and walks you through it one step at a time — declaring your repos in `brain.config.json`,
writing the required core (constitution, vocabulary), mapping domains from the graph, registering the
doc types you want, and building the graph. No git or Python knowledge required (Python just needs to
be present on the machine — the one prerequisite).

### 3. From here on, just talk

There are no commands to learn. Ask questions ("How does checkout work across both apps?"), add
knowledge ("record this decision"), and refresh with **"update the brain."** Under the hood that runs
`pb sync`, but you never have to.

<details>
<summary>The <code>pb</code> commands (for developers who want them)</summary>

With the plugin installed, `pb` is on your `PATH`. Without it, run `python3 <clone>/bin/pb …` — no
PATH edit needed.

```bash
pb sync                          # pull the hub + tracked repos, rebuild the graph
pb adopt ~/dev/backend-api       # move an existing checkout into the hub
pb status                        # quick health check
pb find session                  # look up code symbols in the graph
pb sync --dry-run                # preview without running graphify
pb sync --rebuild                # ignore the cache and rebuild from scratch
```
</details>

`pb adopt <path>` is a one-time migration for developers who already have a repo checked out: it
**moves** that checkout into the hub's `repos/<id>` (keeping history, branches, remote, and
uncommitted work), so there's a single working copy and no drift. After that you develop inside the
hub. See the website's **For developers** guide.

`pb find <term> [aliases…]` searches the built graph for the code symbols a product term maps to
(e.g. `Appointment — app/Models/Appointment.php`). It's what powers **graph-assisted vocabulary** —
so you never have to recall what something is called in code; the graph tells you. Add
`--repo <id>` to scope to one app (e.g. `pb find session --repo backend-api`).

**One combined graph, scoped at query time.** Product Brain keeps a single graph over all repos +
docs — that's what makes cross-app questions and shared communities work. For a focused, accurate
answer about just one app, you *scope* the query (filter to that repo's `source_file` paths) rather
than maintaining a separate graph per repo. Separate-then-merge would actually lose the cross-repo
edges a combined run infers, so it's not the default. (Optional isolated per-repo graphs for very
large/noisy monorepos are noted in the architecture doc's open problems.)

`pb sync` first pulls the hub's own latest changes (only when it's a clean git repo with an upstream),
then pulls each tracked app repo, then rebuilds the graph **incrementally** — graphify caches by
content hash, so only changed files are re-read. Use `--no-hub-pull` to skip the hub pull.

### Upgrading from the script install

Earlier versions installed via `bin/install-skill.sh`, which **copied** the skill into
`~/.claude/skills/brainify` and symlinked `pb` into `~/.local/bin/pb`. If you now install the plugin
on top of that, you'll have **two** brainify skills and **two** `pb`s — and the stale one may win
depending on PATH order. Remove the old install first, then add the plugin. **Your hubs are
untouched** — this only changes how the tooling is installed.

```bash
# 1. Remove the old skill copy/symlink (personal — and project, if you used --project)
rm -rf ~/.claude/skills/brainify
rm -rf ./.claude/skills/brainify        # only if you'd installed with --project

# 2. Remove the old pb symlink so the plugin's pb is the one that runs
rm -f ~/.local/bin/pb
```

Then install the plugin (see [Quick start](#quick-start)) and verify with `pb version` (should run
from the plugin and report up to date) and "set up product brain" (the skill should start its audit).

- If you kept a local clone of this repo **only** to run the installer, you can delete it now — the
  plugin carries everything. Still developing *on the framework*? Keep the clone and `git pull` it.
- The `export PATH=".../.local/bin:…"` line you added to your shell profile is now harmless; leave or
  remove it.
- From here, updates are just `/plugin marketplace update` — no more re-running `install-skill.sh`.

### Versions & updates

The framework version lives in `VERSION` (currently `0.1.7`) and is stamped into the skill's
frontmatter. Check what you have — and whether your installed skill is current — with:

```bash
pb version          # framework version + commit + whether your installed skill matches
pb version --check  # also fetches and tells you if a newer version is available upstream
```

**Plugin (recommended):** update everything — skill *and* `pb` — with `/plugin marketplace update`
in Claude Code. Nothing to re-run.

**Fallback installs:** if you used `bin/install-skill.sh` in copy mode, re-run it after `git pull`;
in `--link` mode (and for the `pb` symlink), a `git pull` in this repo is enough.

### Choose your AI provider (Gemini, Claude, OpenAI, …)

Code and audio/video are processed locally and need no key. Only the document/image pass uses an LLM,
and you choose which one — Product Brain is not tied to Anthropic. Pick a provider per sync or in
`brain.config.json`:

```bash
export GEMINI_API_KEY=your-key       # or GOOGLE_API_KEY
pb sync --provider gemini            # one-off override
```

```json
"graph": { "out": "graph/", "provider": "gemini" }   // persistent, in brain.config.json
```

Supported: `gemini`, `claude`, `openai`, `kimi`, `deepseek`, `ollama` (local), or `auto` (graphify
picks based on whichever key is set). `pb` validates that the chosen provider's key is present before
it does any work, and forces that provider even if other providers' keys are also in your environment.
Keep API keys in environment variables — never commit them to the hub.

That's it. Ask Claude about your product, your code, or your decisions.

---

## What a hub is made of

**The hub is your workspace.** Each app is declared in `brain.config.json` with a git `url`, and
`pb sync` clones it into `repos/<id>` as a **full working clone you develop in** — right next to the
constitution, specs, vocabulary, and graph. Because you work on the live code inside the hub, the
graph is always current — no separate copies to drift out of date. Re-syncs pull each clone only when
it's clean (fast-forward), so your uncommitted work is never touched (`--no-repo-pull` to skip
entirely).

Each repo's `src` lists the source folders worth graphing (e.g. `["app/"]`, `["src/"]`); `pb sync`
tells graphify to skip that repo's other top-level entries (migrations, infra, generated docs…) so
the graph stays focused. Use `["."]` (the default for adopted repos) to graph the whole repo.

**Required core** (this is what makes a directory a "brain"):

- `constitution.md` — the non-negotiable principles.
- `vocabulary.md` — the glossary tying product language to code.

**Recommended:** `domains.md` — the functional areas, owners, status, and which repos implement them. It's graph-assisted: after a sync, the graph's communities are good candidate domains, so you curate rather than author from scratch.

**Extensible docs** — register any doc types you like in `brain.config.json` (`specs`, `decisions`, `meeting-notes`, `research`, `runbooks`, or your own). Markdown is preferred, and graphify connects it automatically.

**Role workflows** — each role gets a lens over the one source: PM, backend, frontend, QA, onboarding.

---

## Method-agnostic by design

Product Brain prescribes **structure**, not **methodology**. Write specs as plain Markdown, RFCs, Shape Up pitches, Spec Kit, or paste exports from Notion — as long as they live under `docs/specs/`, the hub holds and graphs them. Use the tool of your choice.

---

## Markdown-first, but multi-modal

The graph is built with [graphify](https://pypi.org/project/graphifyy/), which parses code locally via tree-sitter and ingests Markdown, PDFs, `.docx`/`.xlsx`, images, and even meeting recordings (transcribed locally). Markdown is preferred for knowledge you author and maintain — it's diffable and free to ingest — but you can drop in native artifacts (a recorded kickoff, a PDF brief) as source material. JSON is used only for machine config (`brain.config.json`). graphify connects related docs and code automatically via inferred edges and communities, so no manual cross-linking is needed. Ask a question and the agent traverses the graph, returning just the few relevant chunks via each node's `source_file` — which is why the graph can live in the hub, away from the code, and still answer.

---

## Tools used

- **[graphify](https://pypi.org/project/graphifyy/)** (`pip install graphifyy`) — local AST + doc knowledge graph.
- **[Claude](https://claude.ai)** (Cowork or Claude Code) — runs `brainify`, answers graph-grounded questions.
- **Your spec method of choice** — optional; Product Brain doesn't require one.

---

## Full documentation

- **[docs/getting-started.md](docs/getting-started.md)** — a no-jargon walkthrough for everyone (start here if you're not technical).
- **[docs/introduction.md](docs/introduction.md)** — what Product Brain is and why, in plain language.
- **[docs/multi-repo-architecture.md](docs/multi-repo-architecture.md)** — the full architecture and open problems.
- **`website/product-brain.html`** — the documentation site (open in a browser).
