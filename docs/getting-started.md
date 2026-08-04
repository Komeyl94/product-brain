# Getting Started with Product Brain

> For everyone — no technical background needed. If you can chat with Claude, you can do this.

---

## The big idea: you can ask Claude to do the commands

You do **not** need to know git, Python, or how to install anything. Whenever a step shows a
command, you can simply **ask Claude to do it** — for example, "install the tools for Product Brain"
or "refresh the brain" — and Claude runs it and tells you what happened in plain words.

The **only** step that might need a technical teammate, once, is creating the hub on a host like
GitHub and signing in the first time. After setup, there are **no commands at all** — you just ask
questions.

---

## Who does what

| Step | You can ask Claude | May need a teammate once |
|---|---|---|
| Add Product Brain to Claude | ✅ (one paste) | — |
| Create the hub folder | ✅ (local) | If it should live on GitHub/GitLab |
| Write your rules, words, decisions | ✅ (Claude interviews you) | — |
| Refresh (build the map) | ✅ | — |
| Ask questions, forever | ✅ | — |

*(The one thing that must already be on the computer is **Python** — the map builder needs it. If it's
missing, Claude tells you the single thing to install, or a teammate installs it once.)*

---

## Step by step

### 1. Add Product Brain to Claude (once)
- **In Claude Code:** paste these three lines. They add everything — the setup wizard *and* the
  behind-the-scenes tool — with nothing to configure:
  ```text
  /plugin marketplace add Whotan/product-brain
  /plugin install product-brain@product-brain
  /reload-plugins
  ```
- **In Cowork:** a teammate adds the **brainify** skill to your claude.ai account once
  (Settings → Features). After that it's available in all your Cowork chats.
- **Check it worked:** type "set up product brain" — if Claude starts a checklist, you're set.

> **Using VS Code, the desktop app, or the web?** You don't repeat this per app. Once your hub is set
> up, it carries a small `.claude/settings.json` that tells *every* Claude surface to load Product
> Brain when you open the hub — the wizard writes it for you. Full details:
> [Using Product Brain in every Claude surface](../README.md#using-product-brain-in-every-claude-surface).

### 2. Create the hub and set it up
Say: **"Set up product brain."** Claude does the technical parts for you — it installs the map
builder if needed, makes the hub, and asks you simple questions one at a time (your rules, your key
words, your product's main areas), writing the files as you go. You review and tweak; nothing is final
until you say so. If you want the hub shared on GitHub, a technical teammate can connect it once.

### 3. Refresh
Ask Claude: **"Update me"** or **"Refresh the brain."** It pulls everyone's latest hub changes and
your apps' latest code, then rebuilds the map. The first time takes a minute or two; after that it's
quick, because it only re-reads what changed.

### 4. Ask anything
That's it. From now on, you and your teammates just ask questions:
- "How does checkout work across both apps?"
- "Why did we choose soft-delete?"
- "Is there a spec for guest checkout yet?"

---

## Handy things to say to Claude

- "Update me" / "Refresh the brain." (pulls the latest and rebuilds the map)
- "Add a new doc type called `retros`."
- "Add a term to the glossary: a 'Reminder' is a scheduled nudge; in code it's `NotificationJob`."
- "Write a spec for password reset using our template."
- "Turn this meeting recording into a note and save it."
- "What should I do next?" (the wizard suggests the most useful next step)

---

## A few common questions

**Do I need to be technical?** No. Setup can be done by asking Claude; after that it's just chatting.

**Will this change our app code?** No. The hub reads your apps; it doesn't add anything to them.

**How often do I refresh?** After meaningful changes, or on a schedule. Repeat refreshes are fast.

**Where do I see a finished example?** Copy `examples/todo-app/` to explore a complete hub.
