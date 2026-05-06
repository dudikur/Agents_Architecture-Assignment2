"""Assignment 2 bot: Gradio by default, CLI with --cli."""

from __future__ import annotations

import argparse
import asyncio
import sys

for _stream in (sys.stdout, sys.stderr, sys.stdin):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

from dotenv import load_dotenv

import memory
from agents_app import format_turn_log, run_turn
from config import build_model


def _messages_to_chatbot_pairs(msgs: list[dict[str, str]]) -> list[list[str]]:
    pairs: list[list[str]] = []
    i = 0
    while i < len(msgs):
        msg = msgs[i]
        if msg.get("role") != "user":
            i += 1
            continue
        user_text = str(msg.get("content", ""))
        assistant_text = ""
        if i + 1 < len(msgs) and msgs[i + 1].get("role") == "assistant":
            assistant_text = str(msgs[i + 1].get("content", ""))
            i += 2
        else:
            i += 1
        pairs.append([user_text, assistant_text])
    return pairs


def _model_banner() -> str:
    try:
        _, label = build_model()
        return f"**Assignment 2 Agents SDK Bot** · model: `{label}` · memory: `history.json`"
    except Exception as exc:
        return f"**Assignment 2 Agents SDK Bot** · configuration error: `{exc}`"


def launch_gradio() -> None:
    try:
        import gradio as gr
    except ImportError as exc:
        raise RuntimeError(
            "Gradio is not installed. Install the full requirements with "
            "`pip install -r requirements.txt`, then run `python main.py` again."
        ) from exc

    load_dotenv(override=True)
    default_md = _model_banner()

    def initial_load() -> tuple[list[list[str]], list[dict[str, str]], dict]:
        msgs = memory.load_messages()
        banner = (
            "**ברוך שובך** — loaded previous conversation from `history.json`."
            if memory.history_exists()
            else default_md
        )
        return _messages_to_chatbot_pairs(msgs), msgs, gr.update(value=banner)

    async def submit(
        message: str, state_messages: list[dict[str, str]] | None
    ) -> tuple[str, list[list[str]], list[dict[str, str]], str, dict]:
        msg = (message or "").strip()
        st = list(state_messages or [])
        if not msg:
            return "", _messages_to_chatbot_pairs(st), st, "", gr.update()

        if msg == "/reset":
            memory.clear_history_file()
            return "", [], [], "Memory reset.", gr.update(value=default_md)

        try:
            result = await run_turn(st, msg)
        except Exception as exc:
            raise gr.Error(f"Error: {exc}") from exc

        memory.save_messages(result.history)
        return (
            "",
            _messages_to_chatbot_pairs(result.history),
            result.history,
            format_turn_log(result),
            gr.update(),
        )

    def do_reset() -> tuple[list[list[str]], list[dict[str, str]], str, dict]:
        memory.clear_history_file()
        return [], [], "Memory reset.", gr.update(value=default_md)

    initial_msgs = memory.load_messages()
    with gr.Blocks(title="Assignment 2 Agents SDK Bot") as demo:
        banner = gr.Markdown(value=default_md)
        chatbot = gr.Chatbot(label="Conversation", height=440, value=_messages_to_chatbot_pairs(initial_msgs))
        state = gr.State(initial_msgs)
        details = gr.Code(label="Router structured output / handoff log", language="json")
        inp = gr.Textbox(
            label="Message",
            placeholder="Example: אני טס ללונדון וצריך לדעת אם לקחת מעיל",
            lines=1,
        )
        with gr.Row():
            send = gr.Button("Send", variant="primary")
            reset = gr.Button("Reset memory")
        gr.Markdown("Use `/reset` to clear `history.json`. CLI also supports `/exit`.")

        demo.load(initial_load, outputs=[chatbot, state, banner])
        inp.submit(submit, inputs=[inp, state], outputs=[inp, chatbot, state, details, banner])
        send.click(submit, inputs=[inp, state], outputs=[inp, chatbot, state, details, banner])
        reset.click(do_reset, outputs=[chatbot, state, details, banner])

    demo.launch()


async def run_cli_async() -> None:
    load_dotenv(override=True)
    had_history = memory.history_exists()
    messages = memory.load_messages()
    if had_history:
        print("ברוך שובך - loaded history.json")

    print(_model_banner().replace("**", ""))
    print("Type a message, /reset to clear memory, /exit to quit.\n")

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue
        if line == "/exit":
            break
        if line == "/reset":
            memory.clear_history_file()
            messages = []
            print("Memory reset.")
            continue

        try:
            result = await run_turn(messages, line)
        except Exception as exc:
            print(f"Error: {exc}")
            continue

        messages = result.history
        memory.save_messages(messages)
        print("\n[Structured router output and handoff]")
        print(format_turn_log(result))
        print("\n[Assistant]")
        print(result.reply)
        print()

    memory.save_messages(messages)


def main() -> None:
    parser = argparse.ArgumentParser(description="Assignment 2 Agents SDK Bot")
    parser.add_argument("--cli", action="store_true", help="Run terminal chat instead of Gradio.")
    args = parser.parse_args()
    if args.cli:
        asyncio.run(run_cli_async())
    else:
        launch_gradio()


if __name__ == "__main__":
    main()
