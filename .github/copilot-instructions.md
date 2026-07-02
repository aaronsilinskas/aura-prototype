## Issue implementation

When assigned a GitHub issue — whether via "assign to agent" on GitHub or in VS Code — follow the `work-on-issue` skill:

```
https://raw.githubusercontent.com/aaronsilinskas/ai-skills/main/skills/engineering/work-on-issue/SKILL.md
```

Fetch and follow that skill precisely.

Additional notes:
- The skills live at `https://github.com/aaronsilinskas/ai-skills/tree/main/skills/engineering`
- The assigned issue number is already known — skip the Step 1 lookup (`dispatch.sh`) and start from the known number.
- You don't have a subagent-dispatch tool: for Step 3 (Implement) and Step 4 (Review), execute the prompt in that step directly as your own instructions instead of dispatching to a fresh subagent.
