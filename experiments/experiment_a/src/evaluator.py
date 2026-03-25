# -*- coding: utf-8 -*-
"""
Evaluation module for Experiment A: ARKE vs SPIRES attribute extraction.

Metrics:
  - Per-attribute exact-match accuracy
  - Per-attribute precision / recall / F1
    (treating "has correct non-null value" as TP)
  - All-attributes-correct rate (only over core attributes)
  - Summary table
"""

from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

from normalizer import normalize_record, EVAL_ATTRIBUTES
from grounder import get_grounder, GROUNDABLE_ATTRS

# Core attributes used for "all-correct" rate
CORE_ATTRIBUTES = ["modality", "anatomy_focus", "laterality", "contrast"]


def _match(pred_val, gold_val) -> bool:
    """
    True if pred matches gold after normalization.
    Both None → True (both agree nothing to extract).
    """
    if pred_val is None and gold_val is None:
        return True
    if pred_val is None or gold_val is None:
        return False
    return pred_val.lower().strip() == gold_val.lower().strip()


def compute_attribute_metrics(
    gold_list: list[dict],
    pred_list: list[dict],
    has_loinc_flags: list[bool],
    system_name: str,
) -> dict:
    """
    Compute per-attribute and overall metrics.

    has_loinc_flags : True = sample has a gold LOINC label,
                      False = label is '없음' (all-null gold)
    """
    n = len(gold_list)
    assert len(pred_list) == n
    assert len(has_loinc_flags) == n

    stats = defaultdict(lambda: {
        "TP": 0, "FP": 0, "FN": 0, "TN": 0,
        "n_gold": 0, "n_pred": 0,
    })

    all_core_correct = 0

    # '없음' group counters: how many all-null samples did SPIRES
    # correctly return nothing for (all attributes null)?
    n_none = sum(1 for f in has_loinc_flags if not f)
    none_all_null_correct = 0   # SPIRES returned all-null for '없음' sample
    none_any_extracted = 0      # SPIRES extracted at least one attr for '없음'

    for gold, pred, has_loinc in zip(gold_list, pred_list, has_loinc_flags):
        core_ok = True
        for attr in EVAL_ATTRIBUTES:
            g = gold.get(attr)
            p = pred.get(attr)
            s = stats[attr]

            if g is not None:
                s["n_gold"] += 1
            if p is not None:
                s["n_pred"] += 1

            if g is not None and p is not None:
                if _match(p, g):
                    s["TP"] += 1
                else:
                    s["FP"] += 1
                    s["FN"] += 1
            elif g is None and p is None:
                s["TN"] += 1
            elif g is None and p is not None:
                s["FP"] += 1
            else:
                s["FN"] += 1

            if attr in CORE_ATTRIBUTES:
                if not _match(p, g):
                    core_ok = False

        if core_ok:
            all_core_correct += 1

        # '없음' sample tracking
        if not has_loinc:
            pred_all_null = all(pred.get(a) is None for a in EVAL_ATTRIBUTES)
            if pred_all_null:
                none_all_null_correct += 1
            else:
                none_any_extracted += 1

    per_attr = {}
    f1_scores = []
    for attr in EVAL_ATTRIBUTES:
        s = stats[attr]
        tp, fp, fn, tn = s["TP"], s["FP"], s["FN"], s["TN"]
        total = tp + fp + fn + tn

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1        = (2 * precision * recall / (precision + recall)
                     if (precision + recall) > 0 else 0.0)
        accuracy  = (tp + tn) / total if total > 0 else 0.0

        per_attr[attr] = {
            "precision": round(precision, 4),
            "recall":    round(recall, 4),
            "f1":        round(f1, 4),
            "accuracy":  round(accuracy, 4),
            "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "n_gold": s["n_gold"],
            "n_pred": s["n_pred"],
        }
        f1_scores.append(f1)

    return {
        "system": system_name,
        "n_samples": n,
        "n_has_loinc": sum(has_loinc_flags),
        "n_no_loinc": n_none,
        "per_attribute": per_attr,
        "all_core_correct_rate": round(all_core_correct / n, 4),
        "all_core_correct_count": all_core_correct,
        "macro_mean_f1": round(sum(f1_scores) / len(f1_scores), 4),
        # '없음' specificity
        "none_correct_rate": round(none_all_null_correct / n_none, 4) if n_none else None,
        "none_correct_count": none_all_null_correct,
        "none_any_extracted": none_any_extracted,
    }


def print_results(results: dict):
    """Pretty-print evaluation results."""
    print(f"\n{'='*70}")
    print(f"  System: {results['system']}  |  N={results['n_samples']} "
          f"(has LOINC: {results['n_has_loinc']}, no LOINC: {results['n_no_loinc']})")
    print(f"{'='*70}")
    print(f"  All-core-attributes-correct rate: "
          f"{results['all_core_correct_rate']:.1%} "
          f"({results['all_core_correct_count']}/{results['n_samples']})")
    print(f"  Macro-mean F1 (all attrs):  {results['macro_mean_f1']:.4f}")
    nr = results.get("none_correct_rate")
    if nr is not None:
        print(f"  No-LOINC all-null rate:     {nr:.1%} "
              f"({results['none_correct_count']}/{results['n_no_loinc']})  "
              f"[SPIRES returned nothing for no-LOINC cases]")
    print()
    print(f"  {'Attribute':<20} {'Prec':>6} {'Rec':>6} {'F1':>6} "
          f"{'Acc':>6}  {'TP':>4} {'FP':>4} {'FN':>4}  "
          f"{'#Gold':>6} {'#Pred':>6}")
    print(f"  {'-'*78}")
    for attr in EVAL_ATTRIBUTES:
        m = results["per_attribute"][attr]
        marker = "*" if attr in CORE_ATTRIBUTES else " "
        print(f"{marker} {attr:<20} "
              f"{m['precision']:>6.3f} {m['recall']:>6.3f} {m['f1']:>6.3f} "
              f"{m['accuracy']:>6.3f}  "
              f"{m['TP']:>4} {m['FP']:>4} {m['FN']:>4}  "
              f"{m['n_gold']:>6} {m['n_pred']:>6}")
    print(f"  (* = core attribute used in all-correct rate: {', '.join(CORE_ATTRIBUTES)})")


def save_results_csv(results: dict, path: Path):
    """Save per-attribute results to CSV."""
    rows = []
    for attr in EVAL_ATTRIBUTES:
        m = results["per_attribute"][attr]
        rows.append({
            "system": results["system"],
            "attribute": attr,
            "is_core": attr in CORE_ATTRIBUTES,
            **m,
        })
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    print(f"  Saved CSV: {path}")


def save_sample_details(gold_list, spires_pred, path: Path,
                         local_names: list[str]):
    """Save per-sample comparison table."""
    rows = []
    for i, (name, gold, sp) in enumerate(
            zip(local_names, gold_list, spires_pred)):
        row = {"idx": i, "local_name": name}
        for attr in EVAL_ATTRIBUTES:
            g = gold.get(attr)
            s = sp.get(attr)
            row[f"gold_{attr}"] = g
            row[f"spires_{attr}"] = s
            row[f"spires_match_{attr}"] = _match(s, g)
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  Saved sample details: {path}")


def compare_systems(arke_results: dict, spires_results: dict) -> pd.DataFrame:
    """Generate a side-by-side comparison DataFrame."""
    rows = []
    for attr in EVAL_ATTRIBUTES:
        a = arke_results["per_attribute"][attr]
        s = spires_results["per_attribute"][attr]
        rows.append({
            "attribute": attr,
            "is_core": attr in CORE_ATTRIBUTES,
            "arke_f1":      a["f1"],
            "spires_f1":    s["f1"],
            "delta_f1":     round(s["f1"] - a["f1"], 4),
            "arke_prec":    a["precision"],
            "spires_prec":  s["precision"],
            "arke_rec":     a["recall"],
            "spires_rec":   s["recall"],
            "arke_acc":     a["accuracy"],
            "spires_acc":   s["accuracy"],
            "n_gold":       a["n_gold"],
        })
    df = pd.DataFrame(rows)
    return df


def compute_sample_level_binary(
    gold_norm: list[dict],
    spires_norm: list[dict],
    has_loinc_flags: list[bool],
    names: list[str],
) -> tuple[dict, pd.DataFrame]:
    """
    Per-sample binary verdict: correct (1) vs incorrect (0).

    Definition of "correct" per sample:
      - has_loinc=True  : ALL 10 evaluated attributes match gold
      - has_loinc=False : SPIRES returns all-null (correctly abstains)

    Returns (binary_metrics_dict, per_sample_df).
    """
    labels, preds, verdicts, rows = [], [], [], []

    for name, gold, pred, has_loinc in zip(
            names, gold_norm, spires_norm, has_loinc_flags):

        # Ground truth positive = has a valid LOINC (something to extract)
        label = 1 if has_loinc else 0

        if has_loinc:
            all_match = all(_match(pred.get(a), gold.get(a))
                            for a in EVAL_ATTRIBUTES)
            predicted_positive = 1   # SPIRES always "attempts" extraction
            correct = 1 if all_match else 0
        else:
            pred_all_null = all(pred.get(a) is None for a in EVAL_ATTRIBUTES)
            predicted_positive = 0 if pred_all_null else 1
            correct = 1 if pred_all_null else 0   # correct = abstained

        labels.append(label)
        preds.append(predicted_positive)
        verdicts.append(correct)

        row = {
            "local_name": name,
            "has_loinc": has_loinc,
            "label_binary": label,
            "pred_binary": predicted_positive,
            "sample_correct": correct,
        }
        for attr in EVAL_ATTRIBUTES:
            row[f"gold_{attr}"] = gold.get(attr)
            row[f"spires_{attr}"] = pred.get(attr)
            row[f"match_{attr}"] = int(_match(pred.get(attr), gold.get(attr)))
        rows.append(row)

    df = pd.DataFrame(rows)

    # Overall binary metrics (correct/incorrect per sample)
    n = len(verdicts)
    correct_total = sum(verdicts)
    overall_accuracy = correct_total / n

    # Precision/Recall/F1 on the "all-attributes-correct" binary label
    # Positive class = sample fully correct
    tp = sum(1 for v in verdicts if v == 1)
    fp = 0   # by definition: if correct=1, it's a true positive
    fn = n - tp
    tn = 0
    # Reframe as binary classification:
    # TP = correct sample, FP = incorrect sample predicted as "would be correct"
    # This doesn't quite make sense in standard form.
    # Better: treat "correct extraction" as the positive class
    # TP = correctly handled (either extracted all right OR abstained)
    # FP = incorrectly handled a no-LOINC sample (extracted something)
    # FN = missed a has-LOINC sample (got attributes wrong)
    # TN = (not applicable here)

    tp2 = sum(1 for v, l in zip(verdicts, labels) if v == 1 and l == 1)
    fp2 = sum(1 for v, l in zip(verdicts, labels) if v == 0 and l == 0
              and preds[verdicts.index(v)] == 1)   # wrong abstain... complex

    # Simpler: standard binary classification metrics
    # predicted_positive=1 means SPIRES extracted something
    # label=1 means there IS a valid LOINC
    tp3 = sum(1 for p, l in zip(preds, labels) if p == 1 and l == 1)
    fp3 = sum(1 for p, l in zip(preds, labels) if p == 1 and l == 0)
    fn3 = sum(1 for p, l in zip(preds, labels) if p == 0 and l == 1)
    tn3 = sum(1 for p, l in zip(preds, labels) if p == 0 and l == 0)

    prec3 = tp3 / (tp3 + fp3) if (tp3 + fp3) > 0 else 0.0
    rec3  = tp3 / (tp3 + fn3) if (tp3 + fn3) > 0 else 0.0
    f1_3  = (2 * prec3 * rec3 / (prec3 + rec3)
             if (prec3 + rec3) > 0 else 0.0)
    acc3  = (tp3 + tn3) / n

    # Per-group accuracy
    has_loinc_correct = sum(v for v, l in zip(verdicts, labels) if l == 1)
    no_loinc_correct  = sum(v for v, l in zip(verdicts, labels) if l == 0)
    n_has = sum(labels)
    n_no  = n - n_has

    binary_metrics = {
        "n_total":            n,
        "n_has_loinc":        n_has,
        "n_no_loinc":         n_no,
        # Sample-level "fully correct" rate
        "sample_accuracy":    round(overall_accuracy, 4),
        "sample_correct":     correct_total,
        # Detection-level (does SPIRES extract vs abstain)
        "detection_accuracy": round(acc3, 4),
        "detection_precision":round(prec3, 4),
        "detection_recall":   round(rec3, 4),
        "detection_f1":       round(f1_3, 4),
        "detection_TP": tp3, "detection_FP": fp3,
        "detection_FN": fn3, "detection_TN": tn3,
        # Per-group
        "has_loinc_all_attr_correct":     has_loinc_correct,
        "has_loinc_all_attr_correct_rate":round(has_loinc_correct / n_has, 4) if n_has else 0,
        "no_loinc_abstain_correct":       no_loinc_correct,
        "no_loinc_abstain_correct_rate":  round(no_loinc_correct / n_no, 4) if n_no else 0,
    }
    return binary_metrics, df


def compute_grounded_metrics(
    raw_gold_records: list[dict],
    spires_norm: list[dict],
    has_loinc_flags: list[bool],
    system_name: str,
) -> dict:
    """
    Attribute-level metrics using RadLex RID comparison for groundable attributes.

    For groundable attrs (modality, anatomy_focus, anatomy_region, laterality,
    guidance_action, guidance_object):
      - Gold RID: taken directly from Playbook (authoritative)
      - Pred RID: ground SPIRES text output via PlaybookGrounder lookup
      - Match: gold_rid == pred_rid  (ontology-level equality)
      - Grounding failure: pred text could not be mapped -> treated as FN

    For non-groundable attrs (contrast, view, timing, reason):
      - Falls back to normalized text comparison (same as text eval).
    """
    grounder = get_grounder()
    n = len(raw_gold_records)

    stats = defaultdict(lambda: {
        "TP": 0, "FP": 0, "FN": 0, "TN": 0,
        "n_gold": 0, "n_pred": 0, "grounding_fail": 0,
    })
    all_core_correct = 0

    for raw_rec, pred_norm, has_loinc in zip(
            raw_gold_records, spires_norm, has_loinc_flags):

        gold_raw = raw_rec["gold"]
        core_ok = True

        for attr in EVAL_ATTRIBUTES:
            s = stats[attr]

            if attr in GROUNDABLE_ATTRS:
                # Gold: use RID from Playbook directly
                gold_rid = gold_raw.get(f"rid_{attr}")
                # Pred: ground extracted text to RID
                pred_text = pred_norm.get(attr)
                pred_rid = grounder.ground(attr, pred_text) if pred_text else None

                if pred_text and not pred_rid:
                    s["grounding_fail"] += 1

                g_val = gold_rid
                p_val = pred_rid
                match = (g_val is not None and p_val is not None
                         and g_val == p_val)
            else:
                # Non-groundable: text comparison
                g_val = normalize_record(gold_raw).get(attr)
                p_val = pred_norm.get(attr)
                match = _match(p_val, g_val)

            if g_val is not None:
                s["n_gold"] += 1
            if p_val is not None:
                s["n_pred"] += 1

            if g_val is not None and p_val is not None:
                if match:
                    s["TP"] += 1
                else:
                    s["FP"] += 1
                    s["FN"] += 1
            elif g_val is None and p_val is None:
                s["TN"] += 1
            elif g_val is None and p_val is not None:
                s["FP"] += 1
            else:
                s["FN"] += 1

            if attr in CORE_ATTRIBUTES:
                if not match and not (g_val is None and p_val is None):
                    core_ok = False
                elif g_val is not None and p_val is None:
                    core_ok = False

        if core_ok:
            all_core_correct += 1

    per_attr = {}
    f1_scores = []
    for attr in EVAL_ATTRIBUTES:
        s = stats[attr]
        tp, fp, fn, tn = s["TP"], s["FP"], s["FN"], s["TN"]
        total = tp + fp + fn + tn
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1        = (2 * precision * recall / (precision + recall)
                     if (precision + recall) > 0 else 0.0)
        accuracy  = (tp + tn) / total if total > 0 else 0.0
        per_attr[attr] = {
            "precision": round(precision, 4),
            "recall":    round(recall, 4),
            "f1":        round(f1, 4),
            "accuracy":  round(accuracy, 4),
            "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "n_gold":          s["n_gold"],
            "n_pred":          s["n_pred"],
            "grounding_fail":  s["grounding_fail"],
            "grounded":        attr in GROUNDABLE_ATTRS,
        }
        f1_scores.append(f1)

    n_none = sum(1 for f in has_loinc_flags if not f)
    return {
        "system":               system_name + " (grounded)",
        "n_samples":            n,
        "n_has_loinc":          sum(has_loinc_flags),
        "n_no_loinc":           n_none,
        "per_attribute":        per_attr,
        "all_core_correct_rate":round(all_core_correct / n, 4),
        "all_core_correct_count": all_core_correct,
        "macro_mean_f1":        round(sum(f1_scores) / len(f1_scores), 4),
        "none_correct_rate":    None,
        "none_correct_count":   0,
        "none_any_extracted":   0,
    }


def run_evaluation(gold_path: Path, spires_cache: Path, out_dir: Path):
    """
    Evaluate SPIRES extraction results against gold standard.
    """
    print("\nLoading gold standard...")
    with open(gold_path, "r", encoding="utf-8") as f:
        gold_records = json.load(f)

    print("Loading SPIRES results...")
    with open(spires_cache, "r", encoding="utf-8") as f:
        spires_raw = json.load(f)

    spires_by_name = {r["local_name"]: r["spires"] for r in spires_raw}

    gold_norm, spires_norm, has_loinc_flags, names = [], [], [], []
    raw_gold_records = []
    missing = 0
    for rec in gold_records:
        name = rec["local_name"]
        if name not in spires_by_name:
            missing += 1
            continue
        names.append(name)
        gold_norm.append(normalize_record(rec["gold"]))
        spires_norm.append(normalize_record(spires_by_name[name]))
        has_loinc_flags.append(rec.get("has_loinc", True))
        raw_gold_records.append(rec)

    print(f"Aligned samples: {len(names)} (missing SPIRES results: {missing})")

    # Attribute-level metrics (text-level)
    spires_metrics = compute_attribute_metrics(
        gold_norm, spires_norm, has_loinc_flags, "SPIRES"
    )
    print_results(spires_metrics)

    # Attribute-level metrics (grounded — RID comparison)
    print("\n[Grounded evaluation — RadLex RID comparison]")
    grounded_metrics = compute_grounded_metrics(
        raw_gold_records, spires_norm, has_loinc_flags, "SPIRES"
    )
    print_results(grounded_metrics)

    # Sample-level binary metrics
    binary_metrics, sample_df = compute_sample_level_binary(
        gold_norm, spires_norm, has_loinc_flags, names
    )

    print(f"\n--- Sample-level binary metrics ---")
    print(f"  Sample fully-correct accuracy : {binary_metrics['sample_accuracy']:.1%}"
          f" ({binary_metrics['sample_correct']}/{binary_metrics['n_total']})")
    print(f"  Has-LOINC: all-attr-correct   : "
          f"{binary_metrics['has_loinc_all_attr_correct_rate']:.1%}"
          f" ({binary_metrics['has_loinc_all_attr_correct']}/{binary_metrics['n_has_loinc']})")
    print(f"  No-LOINC:  abstain-correct    : "
          f"{binary_metrics['no_loinc_abstain_correct_rate']:.1%}"
          f" ({binary_metrics['no_loinc_abstain_correct']}/{binary_metrics['n_no_loinc']})")
    print(f"  Detection precision           : {binary_metrics['detection_precision']:.4f}")
    print(f"  Detection recall              : {binary_metrics['detection_recall']:.4f}")
    print(f"  Detection F1                  : {binary_metrics['detection_f1']:.4f}")

    out_dir.mkdir(parents=True, exist_ok=True)
    save_results_csv(spires_metrics,   out_dir / "spires_metrics_text.csv")
    save_results_csv(grounded_metrics, out_dir / "spires_metrics_grounded.csv")
    save_sample_details(gold_norm, spires_norm,
                        out_dir / "spires_sample_details.csv", names)
    sample_df.to_csv(out_dir / "spires_binary_per_sample.csv",
                     index=False, encoding="utf-8-sig")

    with open(out_dir / "spires_metrics_text.json", "w", encoding="utf-8") as f:
        json.dump(spires_metrics, f, ensure_ascii=False, indent=2)
    with open(out_dir / "spires_metrics_grounded.json", "w", encoding="utf-8") as f:
        json.dump(grounded_metrics, f, ensure_ascii=False, indent=2)
    with open(out_dir / "spires_binary_metrics.json", "w", encoding="utf-8") as f:
        json.dump(binary_metrics, f, ensure_ascii=False, indent=2)

    print(f"\nAll results saved to {out_dir}")
    return (spires_metrics, grounded_metrics, binary_metrics,
            sample_df, names, gold_norm, spires_norm, has_loinc_flags, raw_gold_records)


if __name__ == "__main__":
    RESULTS_DIR = Path(
        "C:/Projects/llm_loinc/SPIRES/experiments/experiment_a/results"
    )
    run_evaluation(
        gold_path=RESULTS_DIR / "gold_standard.json",
        spires_cache=RESULTS_DIR / "spires_cache.json",
        out_dir=RESULTS_DIR,
    )
