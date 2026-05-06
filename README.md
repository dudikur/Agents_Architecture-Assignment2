# Assignment 2 — OpenAI Agents SDK

This project upgrades the Assignment 1 router bot into a real OpenAI Agents SDK system with agents, tools, handoffs, structured output, guardrails, persona, and persistent memory.

## Run

```powershell
cd "C:\Computer Science\Agents\assignment_2"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Set `GEMINI_API_KEY` in `.env`, then run one of:

```powershell
python main.py --cli
python main.py
python run_demo.py --sample
python run_demo.py --live
```

`main.py` starts Gradio by default. `--cli` runs the terminal interface. `run_demo.py --sample` writes an offline sample `execution_log.txt` without using API quota. `run_demo.py --live` runs the real Gemini/Agents SDK demo and can hit Gemini free-tier limits, so it pauses between batches.

## Commands

- `/reset` clears `history.json`.
- `/exit` exits CLI mode.

## Files

- `prompts.py` contains all agent and guardrail prompts.
- `agents_app.py` wires the classifier, triage agent, specialists, handoffs, and turn runner.
- `tools.py` contains deterministic weather, math, and exchange-rate tools.
- `guardrails.py` contains input and output guardrails.
- `docs/architecture.md` is the short explanation document for submission.
