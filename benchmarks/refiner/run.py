#!/usr/bin/env python3
"""Refiner benchmark runner.

Loads test cases from cases.jsonl, runs each through Ollama using a named
profile from profiles.toml, and reports accuracy and timing metrics.

Usage:
    # Run the default profile (echoflow-refiner)
    python benchmarks/refiner/run.py

    # Run the master branch profile
    python benchmarks/refiner/run.py --profile master

    # Save a named baseline
    python benchmarks/refiner/run.py --profile master --save master

    # Compare current profile against a saved baseline
    python benchmarks/refiner/run.py --compare master

    # One-liner: baseline then compare
    make bench-baseline && make bench
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import tomllib
from pathlib import Path

import httpx

BENCH_DIR = Path(__file__).parent
CASES_PATH = BENCH_DIR / "cases.jsonl"
PROFILES_PATH = BENCH_DIR / "profiles.toml"
BASELINES_DIR = BENCH_DIR / "baselines"

DEFAULT_PROFILE = "echoflow-refiner"
DEFAULT_URL = "http://127.0.0.1:11434"


# --- Profiles ---


def load_profile(name: str) -> dict:
    """Load a named profile from profiles.toml."""
    with open(PROFILES_PATH, "rb") as f:
        profiles = tomllib.load(f)

    if name not in profiles:
        available = ", ".join(sorted(profiles.keys()))
        print(f"Error: profile '{name}' not found in {PROFILES_PATH}", file=sys.stderr)
        print(f"Available profiles: {available}", file=sys.stderr)
        sys.exit(1)

    profile = profiles[name]
    return {
        "model": profile["model"],
        "temperature": profile.get("temperature", 0.2),
        "system_prompt": profile.get("system_prompt", ""),
        "user_template": profile.get("user_template", "{transcript}"),
        "description": profile.get("description", ""),
    }


# --- Test cases ---


def load_cases(path: Path) -> list[dict]:
    cases = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


# --- Ollama ---


def run_refine(
    url: str,
    model: str,
    text: str,
    temperature: float,
    system_prompt: str = "",
    user_template: str = "{transcript}",
) -> tuple[str, float]:
    """Send text to Ollama and return (output, elapsed_ms)."""
    user_content = user_template.format(transcript=text)
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    t0 = time.perf_counter()
    resp = httpx.post(
        f"{url}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=60,
    )
    resp.raise_for_status()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    output = resp.json()["message"]["content"].strip()
    return output, elapsed_ms


# --- Comparison ---


def normalize(text: str) -> str:
    """Normalize text for fuzzy comparison: lowercase, collapse whitespace, strip punctuation."""
    text = text.lower().strip()
    text = re.sub(r"[-–—]", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def check_pass(output: str, expected: str) -> bool:
    """Fuzzy comparison — normalized text must match."""
    return normalize(output) == normalize(expected)


def check_length_ratio(output: str, input_text: str) -> float:
    """Return output/input length ratio. >2.0 suggests instruction-following."""
    if not input_text.strip():
        return 0.0
    return len(output) / len(input_text)


# --- Reporting ---


def print_results(results: list[dict], baseline: list[dict] | None = None) -> None:
    baseline_map = {}
    if baseline:
        baseline_map = {r["input"]: r for r in baseline}

    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    timings = [r["refine_ms"] for r in results]

    print(f"\n{'=' * 70}")
    print(f"Results: {passed}/{total} passed ({100 * passed / total:.0f}%)")
    print(f"{'=' * 70}\n")

    for i, r in enumerate(results, 1):
        status = "PASS" if r["pass"] else "FAIL"
        ratio_warn = " [LENGTH!]" if r["length_ratio"] > 2.0 else ""
        print(f"  [{status}] #{i} ({r['category']}){ratio_warn}")
        if not r["pass"]:
            print(f"         input:    {r['input'][:80]}")
            print(f"         expected: {r['expected'][:80]}")
            print(f"         got:      {r['output'][:80]}")
        timing_str = f"{r['refine_ms']:.0f}ms"
        if r["input"] in baseline_map:
            bl = baseline_map[r["input"]]["refine_ms"]
            delta = r["refine_ms"] - bl
            timing_str += f" (baseline: {bl:.0f}ms, delta: {delta:+.0f}ms)"
        print(f"         time: {timing_str}")
        print()

    print(f"Timing:  avg={statistics.mean(timings):.0f}ms  "
          f"p50={statistics.median(timings):.0f}ms  "
          f"p95={sorted(timings)[int(len(timings) * 0.95)]:.0f}ms")

    if baseline:
        bl_timings = [r["refine_ms"] for r in baseline]
        print(f"Baseline: avg={statistics.mean(bl_timings):.0f}ms  "
              f"p50={statistics.median(bl_timings):.0f}ms  "
              f"p95={sorted(bl_timings)[int(len(bl_timings) * 0.95)]:.0f}ms")


# --- Main ---


def main() -> None:
    parser = argparse.ArgumentParser(description="EchoFlow refiner benchmark")
    parser.add_argument(
        "--profile", default=DEFAULT_PROFILE,
        help="Profile name from profiles.toml (default: echoflow-refiner)",
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Ollama base URL")
    parser.add_argument("--cases", default=str(CASES_PATH), help="Path to cases.jsonl")
    parser.add_argument("--save", metavar="NAME", help="Save results as a named baseline")
    parser.add_argument("--compare", metavar="NAME", help="Compare against a named baseline")
    args = parser.parse_args()

    profile = load_profile(args.profile)
    cases = load_cases(Path(args.cases))

    print(f"Profile: {args.profile} — {profile['description']}")
    print(f"  model={profile['model']}  temperature={profile['temperature']}")
    if profile["system_prompt"]:
        print(f"  system_prompt=({len(profile['system_prompt'])} chars)")
    if profile["user_template"] != "{transcript}":
        print(f"  user_template={profile['user_template'][:60]}...")
    print(f"\nRunning {len(cases)} cases...\n")

    # Load baseline for comparison
    baseline = None
    if args.compare:
        baseline_path = BASELINES_DIR / f"{args.compare}.json"
        if not baseline_path.exists():
            print(f"Error: baseline '{args.compare}' not found at {baseline_path}", file=sys.stderr)
            print(f"Run with --save {args.compare} first to create it.", file=sys.stderr)
            sys.exit(1)
        with open(baseline_path) as f:
            baseline = json.load(f)

    # Run benchmark
    results = []
    for i, case in enumerate(cases, 1):
        print(f"  [{i}/{len(cases)}] {case['category']}: {case['input'][:60]}...", end="", flush=True)
        output, elapsed_ms = run_refine(
            args.url,
            profile["model"],
            case["input"],
            temperature=profile["temperature"],
            system_prompt=profile["system_prompt"],
            user_template=profile["user_template"],
        )
        passed = check_pass(output, case["expected"])
        ratio = check_length_ratio(output, case["input"])
        tag = "PASS" if passed else "FAIL"
        warn = " [LENGTH!]" if ratio > 2.0 else ""
        print(f" {tag} ({elapsed_ms:.0f}ms){warn}", flush=True)
        results.append({
            "input": case["input"],
            "expected": case["expected"],
            "output": output,
            "category": case["category"],
            "pass": passed,
            "length_ratio": ratio,
            "refine_ms": elapsed_ms,
        })

    print_results(results, baseline)

    # Save baseline
    if args.save:
        save_path = BASELINES_DIR / f"{args.save}.json"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nBaseline saved: {save_path}")

    # Exit 1 only on a plain run (no --save, no --compare).
    # --save is for capturing data, --compare is for reporting deltas.
    if not args.save and not args.compare and not all(r["pass"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
