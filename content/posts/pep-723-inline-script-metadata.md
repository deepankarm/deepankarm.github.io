---
title: "TIL: Inline dependencies in Python scripts"
date: 2026-01-13T10:00:00+05:30
description: Embed dependencies and Python version requirements directly in your script
tags:
  - python
  - uv
  - til
---

---

When sharing a Python script as a gist, you'd typically include a `requirements.txt` or a `pyproject.toml` with `uv.lock`. Multiple files for one script.

Turns out there's a cleaner way. [PEP 723](https://peps.python.org/pep-0723/) lets you embed dependencies and Python version requirements directly in the script:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests",
#   "rich",
# ]
# ///

import requests
from rich import print

response = requests.get("https://api.github.com/zen")
print(f"[bold green]{response.text}[/bold green]")
```

Run it with [uv](https://docs.astral.sh/uv/):

```bash
uv run script.py
```

`uv` reads the inline metadata, installs the right Python version if needed, creates an isolated environment, installs dependencies, and runs the script. One file, fully self-contained.

---

## The format

The block uses TOML inside comments:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "pandas",
#   "matplotlib>=3.8",
# ]
# ///
```

You can also embed tool-specific config (same `[tool]` table semantics as `pyproject.toml`):

```python
# /// script
# dependencies = ["requests"]
# [tool.uv]
# exclude-newer = "2025-01-01"
# ///
```

---

## Agent skills

This is particularly useful for Claude Code or other agent skills. A skill is just a script that the agent can invoke - having dependencies declared inline means the script is truly portable. No setup instructions, no pyproject.toml, no "first install X", just one file that works.

---
