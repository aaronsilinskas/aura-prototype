# Backlog: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` does this automatically when run inside a clone.

## When a skill says "publish to the backlog"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by the `wayfinder` skill, which charts big work as a **map** issue with **ticket** child-issues. The generic ops above still apply; these are the extras it needs. (Labels — `wayfinder:map`, `wayfinder:<type>` — live in [issue-labels.md](issue-labels.md).)

- **Map** — one issue labelled `wayfinder:map`. Create as any issue (heredoc `--body`).

- **Tickets** — each is a child issue of the map, attached as a **GitHub sub-issue**. Create the issue normally, then attach it under the map. `gh` has no sub-issue subcommand yet, so use the GraphQL API (node ids come from `gh issue view <n> --json id`):

  ```bash
  gh api graphql -f query='
    mutation($map:ID!, $child:ID!) {
      addSubIssue(input:{issueId:$map, subIssueId:$child}) { subIssue { number } }
    }' -f map="<map_node_id>" -f child="<child_node_id>"
  ```

  (The "Add sub-issue" control on the map issue's GitHub page does the same thing, if you prefer the UI.)

- **Blocking** — GitHub has no native dependency link, so a ticket names its blockers in its body:

  ```
  Blocked by #42, #57
  ```

  A ticket is **unblocked** when every issue it names is closed.

- **Frontier** — the map's open sub-issues that are unassigned and unblocked, in number order. List the children via the map's `subIssues` connection, then drop the assigned ones and any whose `Blocked by #…` line still names an open issue:

  ```bash
  gh api graphql -f query='
    query($id:ID!) {
      node(id:$id) { ... on Issue {
        subIssues(first:100) {
          nodes { number title state body assignees(first:1){ totalCount } }
        }
      } }
    }' -f id="<map_node_id>"
  ```

- **Claim** — `gh issue edit <n> --add-assignee @me` before any work.

- **Resolve** — comment the answer, then `gh issue close <n> --comment "..."`, then append a one-line pointer (gist + link) to the map's **Decisions so far** by editing the map body.