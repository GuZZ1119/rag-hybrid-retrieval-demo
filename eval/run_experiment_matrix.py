#!/usr/bin/env python3
"""Run comparable retrieval experiments for text, vector, hybrid, and graph-hybrid paths."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


EVAL_DIR = Path(__file__).resolve().parent
EVALUATOR = EVAL_DIR / "run_retrieval_eval.py"
CONFIGURATIONS: List[Tuple[str, str, str]] = [
    ("TEXT", "TEXT", "disabled"),
    ("VECTOR", "VECTOR", "disabled"),
    ("HYBRID", "HYBRID", "disabled"),
    ("HYBRID+Graph", "HYBRID", "enabled"),
]
DISPLAY_METRICS = [
    "recall_at_1",
    "recall_at_3",
    "recall_at_5",
    "precision_at_3",
    "ndcg_at_5",
    "mrr_at_10",
    "negative_no_answer_rate",
    "graph_evidence_coverage",
]


def format_metric(metric: str, value: Any) -> str:
    if value is None:
        return "-"
    if metric == "mrr_at_10":
        return f"{float(value):.3f}"
    if isinstance(value, float):
        return f"{value * 100:.1f}%"
    return str(value)


def render_matrix(payloads: Dict[str, Dict[str, Any]]) -> str:
    lines = [
        "# Challenge Retrieval Comparison",
        "",
        "This matrix compares the same labelled dataset with graph expansion disabled and enabled.",
        "",
        "| Path | Recall@1 | Recall@3 | Recall@5 | Precision@3 | nDCG@5 | MRR@10 | Negative no-answer | Graph evidence |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, _, _ in CONFIGURATIONS:
        metrics = payloads[label]["metrics"]
        values = [format_metric(metric, metrics.get(metric)) for metric in DISPLAY_METRICS]
        lines.append(f"| {label} | {' | '.join(values)} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the challenge retrieval experiment matrix.")
    parser.add_argument("--api-url", default="http://localhost:8080")
    parser.add_argument("--dataset", type=Path, default=EVAL_DIR / "golden_qa.jsonl")
    parser.add_argument("--fixture-dir", type=Path, default=EVAL_DIR / "fixtures")
    parser.add_argument("--output", type=Path, default=EVAL_DIR / "reports" / "challenge_matrix.md")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--revision", default=None, help="Source commit or revision recorded in every metrics payload.")
    args = parser.parse_args()

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        payloads: Dict[str, Dict[str, Any]] = {}
        for label, mode, graph in CONFIGURATIONS:
            stem = label.lower().replace("+", "_").replace(" ", "_")
            markdown_path = args.output.parent / f"challenge_{stem}.md"
            metrics_path = args.output.parent / f"challenge_{stem}.json"
            command = [
                sys.executable,
                str(EVALUATOR),
                "--api-url", args.api_url,
                "--dataset", str(args.dataset),
                "--fixture-dir", str(args.fixture_dir),
                "--mode", mode,
                "--endpoint", "search",
                "--graph", graph,
                "--top-k", str(args.top_k),
                "--output", str(markdown_path),
                "--metrics-output", str(metrics_path),
            ]
            if args.revision is not None:
                command.extend(["--revision", args.revision])
            if args.bootstrap:
                command.append("--bootstrap")
            subprocess.run(command, check=True)
            payloads[label] = json.loads(metrics_path.read_text(encoding="utf-8"))

        args.output.write_text(render_matrix(payloads), encoding="utf-8")
        print(args.output.read_text(encoding="utf-8"), end="")
        print(f"comparison written to {args.output}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"experiment matrix failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
