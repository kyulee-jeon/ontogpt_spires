# -*- coding: utf-8 -*-
"""
Experiment A: SPIRES Attribute Extraction from Local Radiology Procedure Names

Usage (from experiment_a/ directory):
    python run_experiment_a.py [--mode all|gold|spires|eval]
                               [--model gpt-4o-mini]
                               [--max_samples N]

Modes:
    gold   -- Generate gold standard attributes from Playbook CSV
    spires -- Run SPIRES parser on local procedure names
    eval   -- Evaluate cached SPIRES results against gold (no LLM calls)
    all    -- Run all stages in sequence (default)
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

RESULTS_DIR  = Path(__file__).parent / "results"
GOLD_PATH    = RESULTS_DIR / "gold_standard.json"
SPIRES_CACHE = RESULTS_DIR / "spires_cache.json"


def load_api_key() -> str:
    from dotenv import load_dotenv
    load_dotenv("C:/Projects/llm_loinc/SPIRES/.env")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise EnvironmentError(
            "OPENAI_API_KEY not found. Check C:/Projects/llm_loinc/SPIRES/.env"
        )
    return key


def run_gold():
    from gold_standard import prepare_gold_standard, save_gold_standard
    print("\n[Stage 1] Preparing gold standard attributes...")
    records = prepare_gold_standard()
    save_gold_standard(records)
    return records


def run_spires(records, model: str, max_samples: int = None):
    from spires_runner import SPIRESRunner
    api_key = load_api_key()
    if max_samples:
        records = records[:max_samples]
    print(f"\n[Stage 2] Running SPIRES parser (model={model}, n={len(records)})...")
    runner = SPIRESRunner(model=model, api_key=api_key)
    results = runner.parse_batch(records, cache_path=SPIRES_CACHE, delay=0.5)
    print(f"  SPIRES done: {len(results)} records")
    return results


def run_eval():
    from evaluator import run_evaluation
    from report_generator import generate_report, save_report
    print("\n[Stage 3] Evaluating SPIRES results...")
    result = run_evaluation(
        gold_path=GOLD_PATH,
        spires_cache=SPIRES_CACHE,
        out_dir=RESULTS_DIR,
    )
    (spires_metrics, grounded_metrics, binary_metrics,
     sample_df, names, gold_norm, spires_norm,
     has_loinc_flags, raw_gold_records) = result
    print("\n[Stage 4] Generating markdown report...")
    report = generate_report(
        spires_metrics, grounded_metrics, binary_metrics, sample_df,
        names, gold_norm, spires_norm, has_loinc_flags, raw_gold_records
    )
    save_report(report, RESULTS_DIR / "experiment_a_report.md")
    return result


def main():
    parser = argparse.ArgumentParser(description="Experiment A: SPIRES parsing")
    parser.add_argument("--mode", default="all",
                        choices=["all", "gold", "spires", "eval"])
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--max_samples", type=int, default=None,
                        help="Limit samples for testing (e.g. --max_samples 20)")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    records = None

    if args.mode in ("all", "gold"):
        records = run_gold()

    if args.mode in ("all", "spires"):
        if records is None:
            if GOLD_PATH.exists():
                with open(GOLD_PATH, "r", encoding="utf-8") as f:
                    records = json.load(f)
                print(f"Loaded {len(records)} gold records from {GOLD_PATH}")
            else:
                print("Gold standard not found, running gold stage first...")
                records = run_gold()
        run_spires(records, model=args.model, max_samples=args.max_samples)

    if args.mode in ("all", "eval"):
        run_eval()


if __name__ == "__main__":
    main()
