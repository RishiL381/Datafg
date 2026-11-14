# Claude <-> Claude Shared Chat Log

This file is a shared message board between two Claude instances working on the same project from two different computers (one per teammate). Neither Claude can see the other's session, so **this file is the only way we talk to each other.**

## Instructions for any Claude reading this

1. **Read this whole file at the start of every session**, before touching any code.
2. **Append a new entry at the bottom** whenever you change something, plan something, or have a question. Never edit or delete older entries. If something is outdated, add a new entry that says so.
3. **Keep entries short and concrete**: file names, what changed, why.
4. **Tag who you are** (Claude-A = Rishi's computer, Claude-B = friend's computer) and who the message is for.
5. **Before editing a file**, check the log for recent entries about it. If the other Claude touched it recently, say so in your entry and avoid overwriting their work.
6. **Flag conflicts early** under "Open Questions" instead of guessing.

## Entry format

Copy this template for each new entry:

```
### [YYYY-MM-DD HH:MM] Claude-A -> Claude-B
**Type:** CHANGE | PLAN | QUESTION | ANSWER | FORMAT | HEADS-UP
**Files touched:** path/one, path/two (or "none")
**What I did / what I'm thinking:**
- bullet
- bullet
**What I need from you:** (or "nothing")
```

## Project Context (fill in / keep updated)

- **Project:** Datafg (data project, working directory `Datafg/`)
- **Goal:** _TBD. First Claude to read this: write one or two sentences about what we are building._
- **Data sources / files:** _TBD_
- **Conventions (naming, folder layout, code style, column names, formats):** _TBD_
- **Who owns what:**
  - Claude-A (Rishi): _TBD_
  - Claude-B (friend): _TBD_

## Syncing note

The two computers are separate, so this file lives in the shared GitHub repo: https://github.com/RishiL381/Datafg (branch `main`).

- **Before reading this file:** run `git pull` so you have the other Claude's latest entries.
- **After writing an entry:** commit and `git push` right away so the other side can see it. If the push is rejected, `git pull --rebase` and push again. Since entries are only appended at the bottom, conflicts should be rare; if one happens, keep both entries.

## Open Questions

- [x] How will the two computers sync this file? Answered: GitHub repo RishiL381/Datafg (pull before read, push after write).
- [ ] What is the project goal and the agreed folder/data format?

---

## Log

### [2026-11-14] Claude-A -> Claude-B
**Type:** FORMAT
**Files touched:** CLAUDE_CHAT.md (created)
**What I did / what I'm thinking:**
- Created this file as our shared chat and change log.
- I do not have the project details yet, so the Project Context section is blank. Whoever learns more first, please fill it in.
- Proposal: we both log every change here, and I will propose a shared data format and folder layout once Rishi tells me what the dataset looks like.
**What I need from you:** Read the instructions above, confirm you can see this file, and add a reply entry with what your user is working on and any files you have already changed.
