---
title: "Claude Code hooks for Slack"
date: 2026-01-14T10:00:00+05:30
description: Get notified on Slack when Claude Code completes a task or needs your attention
tags:
  - claude-code
  - slack
  - python
  - automation
---

---

Complex tasks in Claude Code can take a while. Run a few in parallel across different repos and it gets hard to track which ones are done and which ones need input.

Claude Code supports [hooks](https://docs.anthropic.com/en/docs/claude-code/hooks) - shell commands that run in response to events. Hook into the `Stop` and `Notification` events to send a Slack message when a task completes or when Claude needs attention.

---

## The notification script

Using [PEP 723 inline metadata](/posts/pep-723-inline-script-metadata) to keep everything in one file:

```python
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "httpx",
# ]
# ///

import json
import os
import sys

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

def send_slack_message(text: str) -> None:
    if not SLACK_WEBHOOK_URL:
        print("SLACK_WEBHOOK_URL not set", file=sys.stderr)
        return

    import httpx
    httpx.post(SLACK_WEBHOOK_URL, json={"text": text})

def main():
    hook_data = json.load(sys.stdin)
    event = hook_data.get("event")
    cwd = hook_data.get("cwd", "unknown")
    project = cwd.split("/")[-1]

    if event == "stop":
        send_slack_message(f":white_check_mark: Claude Code finished in `{project}`")
    elif event == "notification":
        message = hook_data.get("notification", {}).get("message", "")
        send_slack_message(f":bell: Claude Code needs attention in `{project}`: {message}")

if __name__ == "__main__":
    main()
```

The script reads hook data from stdin (JSON with event type, working directory, etc.), formats a message with the project name, and posts to Slack.

---

## Setting up the webhook

1. Go to [Slack API Apps](https://api.slack.com/apps) and create a new app
2. Enable "Incoming Webhooks"
3. Add a webhook to your workspace and choose a channel
4. Copy the webhook URL

Set it as an environment variable:

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

---

## Configuring Claude Code hooks

Add this to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          "uv run /path/to/claude-code-slack-notify.py"
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          "uv run /path/to/claude-code-slack-notify.py"
        ]
      }
    ]
  }
}
```

Replace `/path/to/claude-code-slack-notify.py` with the actual path.

Now when Claude Code finishes a task or needs input, you get a Slack message with the project name. Useful when running tasks across multiple repos or when you're away from your terminal.

The full gist is [here](https://gist.github.com/deepankarm/1996d1dc9aaa842dd88e45450b83c7e7).

---
