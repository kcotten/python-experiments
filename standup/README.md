# Standup Generator

Builds a daily standup from GitHub, Jira, Confluence and a personal notes
file, and optionally posts it to Slack.

## 1. Install

Requires Python 3.14+ and `requests` (declared in the project's
`pyproject.toml`).

```bash
uv sync
```

## 2. Create the tokens

| Service | What to create | Needed access |
| --- | --- | --- |
| GitHub | Fine-grained personal access token, scoped to the repos you list | Contents: read, Pull requests: read (Metadata is added automatically) |
| Jira + Confluence | One API token from id.atlassian.com → Security → **Create API token** (not the scoped variant) | None; it inherits your account's access |
| Slack | An app with **Incoming Webhooks** turned on, then **Add New Webhook to Workspace** and pick a channel | None; the webhook is created for you |

Notes:

- Use a classic GitHub token with `repo` scope only if the fine-grained
  option doesn't suit you; public repos need no scopes.
- The same Atlassian token works for both Jira and Confluence.
- A Slack webhook is tied to the channel chosen when it was created. To post
  elsewhere, create another webhook.

## 3. Set environment variables

```bash
export GITHUB_TOKEN=...
export JIRA_TOKEN=...
export CONFLUENCE_TOKEN=$JIRA_TOKEN   # same Atlassian token
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Optional, only if ai_summary is enabled in the config
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
```

A source whose token is missing is skipped without an error.

## 4. Configure

On first run the script writes a default `standup_config.json` next to where
you run it. Edit it:

```json
{
  "github": {
    "username": "your-github-login",
    "repos": ["your-github-login/your-repo"]
  },
  "jira": {
    "base_url": "https://yourname.atlassian.net",
    "username": "you@example.com"
  },
  "confluence": {
    "base_url": "https://yourname.atlassian.net",
    "username": "you@example.com"
  },
  "notes": { "file_path": "./daily_notes.md" },
  "slack": { "channel": "#standup-test" }
}
```

- `repos` entries must be `owner/repo`. For personal repos the owner is your
  GitHub login.
- Use the bare site URL for Atlassian, with no `/wiki` suffix.
- `username` for Jira and Confluence is your Atlassian account email.
- Jira's `project_keys` is currently unused; the query returns every issue
  assigned to you.

`standup_config.json` and `daily_notes.md` are in `.gitignore`.

## 5. Write your notes

The script reads `daily_notes.md`. Use one `## YYYY-MM-DD` heading per day,
with `### Completed` and `### Plan` subsections:

```markdown
## 2026-10-23

### Completed
- Fixed the pagination bug

### Plan
- Finish the retry logic
```

- Completed items from the last workday onward are included. On a Monday
  that means Friday.
- Plan items are only read from today's date.
- Bullets under a date with no subsection are treated as completed.

## 6. Run

Run it from this folder so the default config and notes paths resolve.

```bash
python standup.py --dry-run --debug   # fetch and preview, never post
python standup.py                     # print the standup
python standup.py --post              # print and post to Slack
```

Use `--config path/to/config.json` to point at a different config.

## Troubleshooting

- **A section is missing from the output.** A source with no token, or one
  that returns an error, is dropped. Run with `--debug` and look for
  `Error fetching ...: HTTP <status>` lines.
- **GitHub shows no commits.** Commits must be pushed, authored with an email
  linked to your GitHub account, and dated since the last workday. All
  branches are checked.
- **Jira shows nothing.** Issues must be assigned to you and updated since
  the last workday.
- **Confluence `KeyError`.** The config is missing its `confluence` section.
