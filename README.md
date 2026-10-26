# Claude AI Workflows

Agentic workflows I build with [Claude Code](https://claude.com/claude-code). Every project follows the **WAT framework**:

- **Workflows**: Markdown SOPs in `workflows/` that say what to do.
- **Agents**: Claude reads the workflow, makes the decisions and runs the tools in order.
- **Tools**: deterministic Python scripts in `tools/` that do the work.

Secrets stay in each project's `.env`, which is never committed. Each project has a `.env.example` showing the keys it needs.

Each project has its own README explaining how to reuse it for another company, brand or market. Company-specific data is kept out of the repo; each project ships `*.example.*` templates instead.

## Projects

| Project | What it does | Highlights |
|---|---|---|
| [first_agentic_workflow_claude](first_agentic_workflow_claude/) | A repeatable competitor-analysis and market-research workflow that produces a fully branded, source-cited PDF report | Parallel research sub-agents, a JSON-schema data contract, a validator that blocks unsourced claims and dead links, WeasyPrint rendering. Case study and cheat sheet in [`portfolio/`](first_agentic_workflow_claude/portfolio/) |
| [news_letter](news_letter/) | A research-to-inbox newsletter workflow: sourced facts, brand charts, AI hero image, Gmail draft | Brand config, HTML templates, cheat sheet in [`docs/`](news_letter/docs/) |

## Running a project

```bash
cd <project>
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your own keys
```

Then open the folder in Claude Code. Its `CLAUDE.md` tells the agent how to work.
