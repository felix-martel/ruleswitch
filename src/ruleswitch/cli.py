"""The `ruleswitch` command: check, generate, render, diff and evaluate policies.

POLICY is a profile directory, such as `examples/mallow/profiles/fr`. The built-in classifiers read their endpoint and
key from the environment: `RULESWITCH_SYSTEMONE_URL` and `RULESWITCH_SYSTEMONE_KEY`, or `RULESWITCH_LLM_URL` and
`RULESWITCH_LLM_KEY`.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from ruleswitch.check import check
from ruleswitch.diff import diff
from ruleswitch.evaluate import Dataset, evaluate
from ruleswitch.generate import generate
from ruleswitch.judge import Judge, openai_compatible
from ruleswitch.policy import Policy, PolicyError, load
from ruleswitch.render import render
from ruleswitch.systemone import SystemOne
from ruleswitch.types import Classifier


def _load_at(spec: str) -> Policy:
    """A profile directory, or `DIR@REV` for the same directory at a git revision, such as `profiles/fr@HEAD~1`."""
    if "@" not in spec:
        return load(spec)
    path, revision = spec.rsplit("@", 1)
    return load(path, revision=revision)


def _classifier(spec: str, thresholds: dict[str, float]) -> Callable[[Policy], Classifier]:
    """`systemone[:MODEL]`, `judge:MODEL`, or `module:attr`, a factory taking the policy."""
    kind, _, model = spec.partition(":")
    needed = {
        "systemone": ("RULESWITCH_SYSTEMONE_URL", "RULESWITCH_SYSTEMONE_KEY"),
        "judge": ("RULESWITCH_LLM_URL", "RULESWITCH_LLM_KEY"),
    }.get(kind, ())
    if missing := [name for name in needed if name not in os.environ]:
        raise SystemExit(f"--classifier {kind} needs {' and '.join(missing)} in the environment")
    if kind == "systemone":
        url, key = os.environ["RULESWITCH_SYSTEMONE_URL"], os.environ["RULESWITCH_SYSTEMONE_KEY"]
        return lambda p: SystemOne(p, url, key, model or None, thresholds=thresholds, breach=0.5)
    if kind == "judge":
        url, key = os.environ["RULESWITCH_LLM_URL"], os.environ["RULESWITCH_LLM_KEY"]
        return lambda p: Judge(p, openai_compatible(url, key, model))
    return getattr(importlib.import_module(kind), model)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ruleswitch", description=(__doc__ or "").split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="static checks; exit 1 on any problem").add_argument("policy")
    commands.add_parser("generate", help="profile.schema.json and types.py, from structure.yaml").add_argument("policy")
    r = commands.add_parser("render", help="the policy as text")
    r.add_argument("policy")
    r.add_argument("--rendering", choices=["document", "prompt", "judge"], default="document")
    r.add_argument("-o", "--output", help="a file, stdout by default")
    d = commands.add_parser("diff", help="what changed between two versions; DIR@REV reads a git revision")
    d.add_argument("old")
    d.add_argument("new")
    e = commands.add_parser("eval", help="a classifier on a dataset, the policy's own examples by default")
    e.add_argument("policy")
    e.add_argument("--data", help="a JSONL dataset")
    e.add_argument("--classifier", required=True, help="systemone[:MODEL], judge:MODEL or module:attr")
    e.add_argument("--threshold", action="append", default=[], metavar="TIER=P", help="SystemOne tier thresholds")
    e.add_argument("--json", action="store_true", help="the agreement per label as JSON")
    args = parser.parse_args(argv)

    try:
        if args.command == "diff":
            print(diff(_load_at(args.old), _load_at(args.new)))
            return 0
        policy = load(args.policy)
    except PolicyError as error:
        print(error, file=sys.stderr)
        return 1
    if args.command == "check":
        problems = check(policy)
        for problem in problems:
            print(problem)
        return 1 if problems else 0
    if args.command == "generate":
        for name in generate(policy):
            print(f"wrote {policy.root / name}")
        return 0
    if args.command == "render":
        text = render(policy, args.rendering)
        if args.output:
            Path(args.output).write_text(text)
        else:
            print(text, end="")
        return 0
    thresholds = {t: float(p) for t, p in (s.split("=") for s in args.threshold)}
    data = Dataset.load(args.data) if args.data else Dataset.from_policy(policy)
    report = asyncio.run(evaluate(policy, data, _classifier(args.classifier, thresholds)(policy)))
    print(json.dumps(report.agreement()) if args.json else report.markdown(), end="")
    return 0 if all(r.ok for r in report.results) else 1


if __name__ == "__main__":
    sys.exit(main())
