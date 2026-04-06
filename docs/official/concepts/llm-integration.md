# AI Agent Integration

FitOps is built first as a tool you can use directly — run a command, read the output, make decisions. The agent-integration capability is an additional layer, not the primary design goal.

## The Default: Coach-Style Output

When you run a FitOps command, you get readable output by default:

```
$ fitops analytics training-load --today

  CTL (Fitness)    48.3
  ATL (Fatigue)    61.2
  TSB (Form)      -12.9
  Form label       Overreaching — back off or rest
```

No flags required. No parsing. Just information you can act on.

## Adding `--json` for Agents and Scripts

Every command accepts a `--json` flag that switches to structured JSON output. Use this when you want to pipe data into an AI agent, a script, or the local dashboard:

```bash
fitops analytics training-load --today --json
fitops activities list --sport Run --limit 10 --json
fitops analytics vo2max --json
```

When `--json` is used, every response includes a `_meta` block so the agent knows when the data was generated and what filters were applied:

```json
{
  "_meta": {
    "generated_at": "2026-03-11T09:15:00+00:00",
    "total_count": 10,
    "filters_applied": { "sport_type": "Run", "limit": 10 }
  },
  "activities": [ ... ]
}
```

Values carry explicit units so an agent can reason about them without guessing:

```json
"distance": {
  "meters": 10234.0,
  "km": 10.23,
  "miles": 6.35
}
```

## Feeding Data to an AI

Combine multiple commands and pipe the output into your AI assistant:

```bash
echo "=== Training Load ===" && fitops analytics training-load --today --json
echo "=== VO2max ===" && fitops analytics vo2max --json
echo "=== Recent runs ===" && fitops activities list --sport Run --limit 10 --json
```

Paste the combined output with a prompt like:

> "Based on this training data, am I ready to race this weekend?"

Or use the `fitops notes` command to build a persistent memory layer for your agent — notes survive across sessions and can be tagged, linked to activities, and recalled by tag:

```bash
fitops notes list --tag pattern        # recall flagged patterns
fitops notes get hr-drift-march-2026   # read a specific observation
```

## Form and Zone Labels

JSON output includes text labels alongside numbers, so an agent gets human-readable context alongside the raw values:

```json
"form_label": "Overreaching — back off or rest"
"ramp_label": "Moderate build"
```

## When to Use Which Mode

| Situation | Use |
|-----------|-----|
| Checking your training at the terminal | Default (no flag) |
| Asking an AI "how am I doing?" | `--json` + paste output |
| Scripting a daily snapshot | `--json` + pipe to file or agent |
| Browsing visually | `fitops dashboard serve` |
| Persisting coaching observations | `fitops notes create` |

---

## Setting Up FitOps as a Skill in Your AI Agent

FitOps ships a ready-to-use skill file that gives any AI assistant full context on the CLI commands, output format, and coaching patterns — without you having to re-explain it each session.

The skill file is at `docs/official/fitops-skill.md` in the repo, or you can grab it from the [GitHub releases page](https://github.com/BrunoV21/FitOps-CLI/releases).

### Claude Code

Claude Code loads project-level slash commands from `.claude/commands/`. Drop the skill file there:

```bash
mkdir -p .claude/commands
cp fitops-skill.md .claude/commands/fitops.md
```

Then in any Claude Code session in that directory:

```
/fitops What's my current fitness level?
```

You can also add it as global context in `~/.claude/CLAUDE.md` so it's available everywhere — useful if you use FitOps across multiple projects.

### Codex (OpenAI CLI)

Codex reads `AGENTS.md` from the current directory (and parent directories up to repo root). Put the skill content in an `AGENTS.md`:

```bash
cp fitops-skill.md AGENTS.md
```

Or append it if you already have an `AGENTS.md`:

```bash
cat fitops-skill.md >> AGENTS.md
```

Codex will load it automatically on the next session in that directory.

### OpenCode (sst.dev)

OpenCode reads instructions from `AGENTS.md` and rules from `.rules` files in the project root:

```bash
cp fitops-skill.md AGENTS.md
# or add to an existing AGENTS.md
```

Alternatively, create a `.rules` file for always-on context:

```bash
cp fitops-skill.md .rules
```

### Cursor

Add a Cursor rule to apply FitOps context to any session:

```bash
mkdir -p .cursor/rules
cp fitops-skill.md .cursor/rules/fitops.mdc
```

The `.mdc` format is standard Markdown — no changes needed to the file. Cursor picks up all `.mdc` files in `.cursor/rules/` automatically.

For a project where FitOps is a core tool, you can also paste the skill content into Cursor's global rules at **Settings → General → Rules for AI**.

### Aider

Add the skill file as a read-only context file via `.aider.conf.yml`:

```yaml
# .aider.conf.yml
read:
  - fitops-skill.md
```

Or pass it directly on the command line:

```bash
aider --read fitops-skill.md
```

### Any Other Agent

The skill file is plain Markdown. You can paste it into any system prompt, context window, or instructions field:

- **ChatGPT / Claude.ai**: paste as a system message or first user message
- **Cursor AI chat**: paste into the context before asking
- **Zed AI**: add to your assistant instructions
- Any agent that accepts a system prompt or context file

---

## The FitOps Skill File

The skill covers:
- Every command group (`auth`, `sync`, `activities`, `athlete`, `analytics`, `workouts`, `race`, `weather`, `notes`, `dashboard`)
- Full flags and output fields for each command
- How to chain commands for common workflows (fitness check, zone setup, VO2max, overtraining assessment)
- Error recovery patterns (no activities → sync, no zones → infer, etc.)
- How to interpret key metrics (TSB form zones, ACWR bands, HR drift %, WAP factors, WBGT heat flags)
- The agent memory pattern using `fitops notes`

← [Concepts](./index.md)
