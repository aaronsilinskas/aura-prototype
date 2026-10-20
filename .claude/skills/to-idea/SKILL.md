---
name: to-idea
description: Park a discovery or new idea as a short issue to revisit later, without derailing the current task. A quick stub, not a fleshed-out spec.
argument-hint: "the idea to capture (or leave blank to pull it from the conversation)"
disable-model-invocation: true
---

# To Idea

Capture a discovery or new idea as an issue so it isn't lost, without stopping to flesh it out. This is deliberately a **stub, not a spec**: just enough to remember the idea and why it mattered, so a future session can pick it up.

Do **not** interview or grill the idea into shape. Synthesize what's already known, publish, and return to the original work.

The issue tracker and triage label vocabulary should have been provided to you. If not, tell the user to run `/setup-matt-pocock-skills`.

`idea` is a role, like the triage roles. Its label string comes from the `idea` row in `docs/agents/triage-labels.md`. If that file or the row is missing, use the label `idea`.

## Process

1. **Draft a short issue.**
   - **Title:** a concise, recognizable summary of the idea.
   - **Body:** 2 to 4 sentences. Say what the idea is, what triggered it (the discovery or context it came out of), and give a one-line "to explore later" pointer. Link any related issue, PR, or discussion by number or URL instead of restating it. Use the project's domain glossary vocabulary. Leave out file paths and code snippets, because they go stale. The point is to remember the idea, not spec it.

2. **Publish it** to the project issue tracker, using the issue tracker docs you were given, with **only** the label resolved for the `idea` role. Do **not** apply the `ready-for-agent` role, a category, or any other triage label. An idea is a raw parking-lot entry, not a triaged or specified task.

3. **Report** the issue URL and return to what you were doing.

## Not a spec

The `idea` role's label keeps these distinct from specs and ready-for-agent work. An idea is a placeholder to look into later. Fleshing it out happens *when you revisit it*, not now. That's when it graduates into a real spec and implementation tickets: tell the user to run `/to-spec` (or `/grill-with-docs` to grill it first).
