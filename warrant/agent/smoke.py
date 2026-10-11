"""Run one question from a configuration against the real model.

    uv run python -m warrant.agent.smoke --config <configuration> --question <question id>

The only command that calls a model. Ask the project lead before running it, and keep credentials
in a local AWS profile or environment variables.
"""

import argparse
import dataclasses
from pathlib import Path

from warrant.agent.claude import ClaudeAgent
from warrant.config import data_dir
from warrant.write_line.config import load_config
from warrant.write_line.run import run


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run one question against the real model.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--question", required=True)
    parser.add_argument("--rule", default="empty")
    parser.add_argument("--work-dir", type=Path, default=data_dir() / "smoke")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if config.model is None:
        print(f"{args.config} names no model block")
        return 2
    question = next((q for q in config.questions if q.id == args.question), None)
    if question is None:
        print(f"{args.config} names no question {args.question!r}")
        return 2

    one = dataclasses.replace(config, questions=(question,), rules=(args.rule,), runs=1)
    (row,) = run(one, ClaudeAgent(one.model), args.work_dir).rows

    print(f"question: {row.question_id} (rule {row.rule})")
    print(f"response: {row.response_class}{f' - {row.failure}' if row.failure else ''}")
    print(f"final SQL: {row.final_sql}")
    print(f"executed: {row.executed}")
    print(f"tokens: {row.usage.input_tokens} in, {row.usage.output_tokens} out")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
