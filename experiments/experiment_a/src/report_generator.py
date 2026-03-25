# -*- coding: utf-8 -*-
"""
Markdown report generator for Experiment A: SPIRES attribute extraction analysis.
Produces a detailed, example-rich analysis report.
"""

from __future__ import annotations
import json
from collections import defaultdict, Counter
from pathlib import Path
from datetime import date

from normalizer import EVAL_ATTRIBUTES, normalize_record
from evaluator import CORE_ATTRIBUTES, _match as attr_match

RESULTS_DIR = Path("C:/Projects/llm_loinc/SPIRES/experiments/experiment_a/results")


def _fmt_val(v):
    return f"`{v}`" if v else "_null_"


def _get_errors(gold_norm, spires_norm, has_loinc_flags, names, raw_gold_records):
    """Collect per-sample per-attribute error info."""
    rows = []
    for name, gold, pred, has_loinc, raw in zip(
            names, gold_norm, spires_norm, has_loinc_flags, raw_gold_records):
        mismatches = {}
        for attr in EVAL_ATTRIBUTES:
            g = gold.get(attr)
            p = pred.get(attr)
            if not attr_match(p, g):
                mismatches[attr] = {"gold": g, "pred": p}
        rows.append({
            "name": name,
            "has_loinc": has_loinc,
            "loinc_num": raw["gold"].get("loinc_num"),
            "lcn": raw["gold"].get("long_common_name"),
            "mismatches": mismatches,
            "n_mismatches": len(mismatches),
            "gold": gold,
            "pred": pred,
        })
    return rows


def generate_report(
    spires_metrics: dict,
    grounded_metrics: dict,
    binary_metrics: dict,
    sample_df,
    names: list,
    gold_norm: list,
    spires_norm: list,
    has_loinc_flags: list,
    raw_gold_records: list,
) -> str:

    errors = _get_errors(gold_norm, spires_norm, has_loinc_flags,
                          names, raw_gold_records)
    n_total = spires_metrics["n_samples"]
    n_has   = spires_metrics["n_has_loinc"]
    n_no    = spires_metrics["n_no_loinc"]

    # -------------------------------------------------------------------
    # Collect examples for each error pattern
    # -------------------------------------------------------------------
    # Fully correct (has_loinc)
    correct_examples = [e for e in errors if e["has_loinc"] and e["n_mismatches"] == 0]
    # Fully wrong (has_loinc, all 10 attrs wrong or null)
    bad_examples = sorted(
        [e for e in errors if e["has_loinc"]],
        key=lambda x: -x["n_mismatches"]
    )
    # No-LOINC correctly abstained
    abstain_correct = [e for e in errors if not e["has_loinc"] and e["n_mismatches"] == 0]
    # No-LOINC hallucinated
    abstain_wrong   = [e for e in errors if not e["has_loinc"] and e["n_mismatches"] > 0]

    # Per-attribute error examples
    attr_fp_examples = defaultdict(list)  # FP: gold=None, pred=something
    attr_fn_examples = defaultdict(list)  # FN: gold=X, pred=None
    attr_mismatch_examples = defaultdict(list)  # gold=X, pred=Y

    for e in errors:
        for attr, mm in e["mismatches"].items():
            g, p = mm["gold"], mm["pred"]
            entry = {"name": e["name"], "lcn": e["lcn"], "gold": g, "pred": p}
            if g is None and p is not None:
                attr_fp_examples[attr].append(entry)
            elif g is not None and p is None:
                attr_fn_examples[attr].append(entry)
            else:
                attr_mismatch_examples[attr].append(entry)

    # Most common modality errors
    modality_errors = [
        e for e in errors if e["has_loinc"] and "modality" in e["mismatches"]
    ]
    modality_fn = [e for e in modality_errors
                   if e["mismatches"]["modality"]["pred"] is None]

    # -------------------------------------------------------------------
    # Build report
    # -------------------------------------------------------------------
    lines = []
    A = lines.append  # shorthand

    A(f"# Experiment A: SPIRES Attribute Extraction Analysis")
    A(f"")
    A(f"**Date**: {date.today()}  ")
    A(f"**Model**: gpt-4o-mini  ")
    A(f"**Dataset**: SNUH local radiology order names (`snuh_250926.xlsx`)  ")
    A(f"**Gold standard**: LOINC/RSNA Radiology Playbook  ")
    A(f"")

    # ---------------------------------------------------------------
    A(f"---")
    A(f"")
    A(f"## 1. Method Description")
    A(f"")
    A(f"### 1.1 SPIRES (Structured Prompt Interrogation and Recursive Extraction from Schemas)")
    A(f"")
    A(f"SPIRES is the core extraction engine of [OntoGPT](https://github.com/monarch-initiative/ontogpt).")
    A(f"It uses zero-shot LLM prompting guided by a **LinkML schema** to extract structured")
    A(f"knowledge from free text. The pipeline consists of four stages:")
    A(f"")
    A(f"| Stage | Description |")
    A(f"|-------|-------------|")
    A(f"| **GeneratePrompt** | Converts the LinkML schema into a pseudo-YAML template prompt. Each attribute becomes a named field with a natural-language description as the prompt cue. |")
    A(f"| **CompletePrompt** | Sends the prompt + input text to the LLM (gpt-4o-mini). The LLM fills in the pseudo-YAML template. |")
    A(f"| **ParseCompletion** | Parses the LLM's YAML-formatted response field by field. For nested/complex types, SPIRES calls itself recursively. |")
    A(f"| **Ground** | Maps extracted text values to ontology identifiers (e.g., RadLex RIDs). *(Not applied in this experiment — text-level comparison only.)* |")
    A(f"")
    A(f"### 1.2 Schema Design")
    A(f"")
    A(f"A custom LinkML schema (`radiology_procedure.yaml`) was created with the following attributes:")
    A(f"")
    A(f"| Attribute | Description | Example values |")
    A(f"|-----------|-------------|----------------|")
    A(f"| `modality` | Imaging modality abbreviation | CT, MR, US, XR, RF, NM, PET, MG |")
    A(f"| `anatomy_focus` | Most specific anatomic target | brain, knee, ureter |")
    A(f"| `anatomy_region` | Broader anatomic region | chest, abdomen, lower extremity |")
    A(f"| `laterality` | Body side | left, right, bilateral, unspecified |")
    A(f"| `contrast` | Contrast administration | W, WO, W_WO |")
    A(f"| `view` | View type / count | AP, Lateral, 2 views |")
    A(f"| `guidance_action` | Interventional action | biopsy, injection, placement |")
    A(f"| `guidance_object` | Target of intervention | nerve, stent, mass |")
    A(f"| `timing` | Temporal context | pre-procedure, dynamic |")
    A(f"| `reason` | Clinical indication | trauma, metastasis |")
    A(f"")
    A(f"### 1.3 Gold Standard Derivation")
    A(f"")
    A(f"Gold-standard attributes were derived from the **LOINC/RSNA Radiology Playbook CSV**")
    A(f"(`LoincRsnaRadiologyPlaybook.csv`) by joining each labeled LOINC code with its")
    A(f"structured `PartTypeName` / `PartName` rows:")
    A(f"")
    A(f"- `Rad.Modality.Modality Type` -> `modality`")
    A(f"- `Rad.Anatomic Location.Imaging Focus` -> `anatomy_focus` (most specific)")
    A(f"- `Rad.Anatomic Location.Region Imaged` -> `anatomy_region`")
    A(f"- `Rad.Anatomic Location.Laterality` -> `laterality`")
    A(f"- Contrast (`W`/`WO`/`W_WO`) was inferred from the LOINC Long Common Name via regex")
    A(f"  (e.g., `W contrast IV` -> W, `WO contrast` -> WO, `W and WO` -> W_WO)")
    A(f"- `Rad.Guidance for.Action` -> `guidance_action`")
    A(f"- `Rad.Guidance for.Object` -> `guidance_object`")
    A(f"")
    A(f"For samples labeled **없음** (no LOINC match), all gold attributes are null.")
    A(f"SPIRES is expected to return all-null for these cases (abstain correctly).")
    A(f"")
    A(f"### 1.4 Evaluation Setup")
    A(f"")
    A(f"- **Normalization**: both gold and predicted values were lowercased and synonym-mapped")
    A(f"  before comparison (e.g., `MRI` -> `MR`, `Rt` -> `right`, `thyroid` ~ `thyroid gland`).")
    A(f"- **Exact match**: predicted value == gold value after normalization (both null = match).")
    A(f"- **Core attributes**: modality, anatomy_focus, laterality, contrast")
    A(f"  (used for the all-core-correct rate and sample-level binary verdict).")
    A(f"")

    # ---------------------------------------------------------------
    A(f"---")
    A(f"")
    A(f"## 2. Dataset")
    A(f"")
    A(f"| Split | Count |")
    A(f"|-------|-------|")
    A(f"| Total samples | {n_total} |")
    A(f"| Has valid LOINC label | {n_has} |")
    A(f"| Label = 없음 (no LOINC) | {n_no} |")
    A(f"| Missing SPIRES results | {290 - n_total} |")
    A(f"")

    # ---------------------------------------------------------------
    A(f"---")
    A(f"")
    A(f"## 3. Overall Results")
    A(f"")
    A(f"### 3.1 Sample-level Binary Metrics")
    A(f"")
    A(f"A sample is **correct** if:")
    A(f"- Has-LOINC case: ALL 10 evaluated attributes exactly match gold")
    A(f"- No-LOINC case: SPIRES returns all-null (correctly abstains)")
    A(f"")
    A(f"| Metric | Value |")
    A(f"|--------|-------|")
    sa = binary_metrics['sample_accuracy']
    sc = binary_metrics['sample_correct']
    A(f"| Overall sample accuracy | **{sa:.1%}** ({sc}/{n_total}) |")
    hc = binary_metrics['has_loinc_all_attr_correct_rate']
    hcc = binary_metrics['has_loinc_all_attr_correct']
    A(f"| Has-LOINC: all-attr-correct rate | {hc:.1%} ({hcc}/{n_has}) |")
    nc = binary_metrics['no_loinc_abstain_correct_rate']
    ncc = binary_metrics['no_loinc_abstain_correct']
    A(f"| No-LOINC: abstain-correct rate | {nc:.1%} ({ncc}/{n_no}) |")
    A(f"")
    A(f"**Detection-level metrics** (does SPIRES extract vs. abstain correctly?)")
    A(f"")
    A(f"| Metric | Value |")
    A(f"|--------|-------|")
    A(f"| Accuracy | {binary_metrics['detection_accuracy']:.4f} |")
    A(f"| Precision | {binary_metrics['detection_precision']:.4f} |")
    A(f"| Recall | {binary_metrics['detection_recall']:.4f} |")
    A(f"| F1 | {binary_metrics['detection_f1']:.4f} |")
    A(f"| TP (correctly extracted) | {binary_metrics['detection_TP']} |")
    A(f"| FP (extracted for no-LOINC) | {binary_metrics['detection_FP']} |")
    A(f"| FN (failed to extract for has-LOINC) | {binary_metrics['detection_FN']} |")
    A(f"| TN (correctly abstained) | {binary_metrics['detection_TN']} |")
    A(f"")

    A(f"### 3.2 Attribute-level Metrics: Text vs Grounded (All {n_total} Samples)")
    A(f"")
    A(f"Two evaluations are reported:")
    A(f"- **Text**: normalized string comparison (e.g., `thyroid` vs `thyroid gland` = mismatch)")
    A(f"- **Grounded**: RadLex RID comparison via Playbook lookup (e.g., both `thyroid` and `thyroid gland` -> RID7578 = match)")
    A(f"")
    A(f"#### Text-level")
    A(f"")
    A(f"")
    A(f"| Attribute | #Gold | #Pred | TP | FP | FN | TN | Prec | Rec | F1 | Acc |")
    A(f"|-----------|------:|------:|---:|---:|---:|---:|-----:|----:|---:|----:|")
    for attr in EVAL_ATTRIBUTES:
        m = spires_metrics["per_attribute"][attr]
        marker = " *" if attr in CORE_ATTRIBUTES else ""
        A(f"| `{attr}`{marker} | {m['n_gold']} | {m['n_pred']} | "
          f"{m['TP']} | {m['FP']} | {m['FN']} | {m['TN']} | "
          f"{m['precision']:.3f} | {m['recall']:.3f} | **{m['f1']:.3f}** | {m['accuracy']:.3f} |")
    A(f"")
    A(f"> `*` = core attribute | `G` = grounded (RID comparison) | `-` = text comparison")
    A(f"")
    A(f"#### Grounded-level (RadLex RID comparison)")
    A(f"")
    A(f"| Attribute | #Gold | #Pred | Grnd Fail | TP | FP | FN | TN | Prec | Rec | F1 | Acc |")
    A(f"|-----------|------:|------:|----------:|---:|---:|---:|---:|-----:|----:|---:|----:|")
    for attr in EVAL_ATTRIBUTES:
        mg = grounded_metrics["per_attribute"][attr]
        is_grounded = mg.get("grounded", False)
        marker = " * G" if attr in CORE_ATTRIBUTES and is_grounded else (" * " if attr in CORE_ATTRIBUTES else (" G" if is_grounded else ""))
        gf = mg.get("grounding_fail", 0)
        A(f"| `{attr}`{marker} | {mg['n_gold']} | {mg['n_pred']} | {gf} | "
          f"{mg['TP']} | {mg['FP']} | {mg['FN']} | {mg['TN']} | "
          f"{mg['precision']:.3f} | {mg['recall']:.3f} | **{mg['f1']:.3f}** | {mg['accuracy']:.3f} |")
    A(f"")
    A(f"> **Grounded macro-mean F1**: {grounded_metrics['macro_mean_f1']:.4f}")
    A(f">")
    A(f"> **Grounded all-core-correct rate**: {grounded_metrics['all_core_correct_rate']:.1%} "
      f"({grounded_metrics['all_core_correct_count']}/{n_total})")
    A(f"")
    A(f"> `*` = core attribute used in all-correct rate")
    A(f">")
    A(f"> **Macro-mean F1**: {spires_metrics['macro_mean_f1']:.4f}")
    A(f">")
    A(f"> **All-core-correct rate**: {spires_metrics['all_core_correct_rate']:.1%} "
      f"({spires_metrics['all_core_correct_count']}/{n_total})")
    A(f">")
    A(f"> **No-LOINC all-null rate**: {spires_metrics['none_correct_rate']:.1%} "
      f"({spires_metrics['none_correct_count']}/{n_no})")
    A(f"")

    # ---------------------------------------------------------------
    A(f"---")
    A(f"")
    A(f"## 4. Per-Attribute Deep Dive")
    A(f"")

    # --- modality ---
    m = spires_metrics["per_attribute"]["modality"]
    A(f"### 4.1 Modality  (F1={m['f1']:.3f}, Prec={m['precision']:.3f}, Rec={m['recall']:.3f})")
    A(f"")
    A(f"Modality is the most important attribute. Precision is high ({m['precision']:.3f}) — when SPIRES")
    A(f"extracts a modality it is usually correct — but recall is lower ({m['recall']:.3f}),")
    A(f"meaning SPIRES often **fails to infer modality** when it is not explicitly stated.")
    A(f"")
    A(f"**FN={m['FN']}: Cases where modality was not extracted (gold had a value, SPIRES returned null)**")
    A(f"")
    A(f"Most common pattern: **implicit modality** — the procedure name contains no standard abbreviation.")
    A(f"")
    fn_mod = attr_fn_examples.get("modality", [])[:8]
    if fn_mod:
        A(f"| Local name | Gold modality | SPIRES output |")
        A(f"|------------|--------------|---------------|")
        for ex in fn_mod:
            A(f"| `{ex['name']}` | `{ex['gold']}` | {_fmt_val(ex['pred'])} |")
    A(f"")
    A(f"**FP={m['FP']}: Cases where SPIRES extracted a modality but gold had none**")
    fp_mod = attr_fp_examples.get("modality", [])[:5]
    if fp_mod:
        A(f"| Local name | Gold | SPIRES |")
        A(f"|------------|------|--------|")
        for ex in fp_mod:
            A(f"| `{ex['name']}` | {_fmt_val(ex['gold'])} | `{ex['pred']}` |")
    else:
        A(f"_(none or very few)_")
    A(f"")
    mm_mod = attr_mismatch_examples.get("modality", [])[:5]
    if mm_mod:
        A(f"**Wrong modality (both non-null but mismatched)**")
        A(f"")
        A(f"| Local name | Gold | SPIRES |")
        A(f"|------------|------|--------|")
        for ex in mm_mod:
            A(f"| `{ex['name']}` | `{ex['gold']}` | `{ex['pred']}` |")
        A(f"")

    # --- anatomy_focus ---
    m = spires_metrics["per_attribute"]["anatomy_focus"]
    A(f"### 4.2 Anatomy Focus  (F1={m['f1']:.3f}, Prec={m['precision']:.3f}, Rec={m['recall']:.3f})")
    A(f"")
    A(f"Anatomy focus is the most specific anatomic target. The main failure modes are:")
    A(f"1. **Expression mismatch**: SPIRES uses a different but valid term (e.g., `thyroid` vs `thyroid gland`)")
    A(f"2. **Focus/Region confusion**: SPIRES puts the focus into `anatomy_region` and vice versa")
    A(f"3. **Over-specificity**: SPIRES picks a sub-structure not listed in the Playbook")
    A(f"")
    mm_af = attr_mismatch_examples.get("anatomy_focus", [])[:8]
    if mm_af:
        A(f"**Examples of expression mismatch:**")
        A(f"")
        A(f"| Local name | Gold focus | SPIRES focus |")
        A(f"|------------|-----------|--------------|")
        for ex in mm_af:
            A(f"| `{ex['name']}` | {_fmt_val(ex['gold'])} | {_fmt_val(ex['pred'])} |")
    A(f"")
    fn_af = attr_fn_examples.get("anatomy_focus", [])[:5]
    if fn_af:
        A(f"**Missed anatomy focus (gold has value, SPIRES returned null):**")
        A(f"")
        A(f"| Local name | Gold focus | LOINC LCN |")
        A(f"|------------|-----------|-----------|")
        for ex in fn_af:
            A(f"| `{ex['name']}` | {_fmt_val(ex['gold'])} | `{ex.get('lcn','')}` |")
    A(f"")

    # --- laterality ---
    m = spires_metrics["per_attribute"]["laterality"]
    A(f"### 4.3 Laterality  (F1={m['f1']:.3f}, Prec={m['precision']:.3f}, Rec={m['recall']:.3f})")
    A(f"")
    A(f"Recall is high ({m['recall']:.3f}) — SPIRES rarely misses laterality when present —")
    A(f"but precision is low ({m['precision']:.3f}) due to **over-extraction**: SPIRES assigns")
    A(f"`unspecified` to non-lateralized organs, generating FP={m['FP']}.")
    A(f"")
    fp_lat = attr_fp_examples.get("laterality", [])[:8]
    if fp_lat:
        A(f"**FP examples (gold=null, SPIRES extracted a laterality):**")
        A(f"")
        A(f"| Local name | Gold | SPIRES |")
        A(f"|------------|------|--------|")
        for ex in fp_lat:
            A(f"| `{ex['name']}` | {_fmt_val(ex['gold'])} | `{ex['pred']}` |")
    A(f"")
    mm_lat = attr_mismatch_examples.get("laterality", [])[:5]
    if mm_lat:
        A(f"**Wrong laterality value:**")
        A(f"")
        A(f"| Local name | Gold | SPIRES |")
        A(f"|------------|------|--------|")
        for ex in mm_lat:
            A(f"| `{ex['name']}` | `{ex['gold']}` | `{ex['pred']}` |")
    A(f"")

    # --- contrast ---
    m = spires_metrics["per_attribute"]["contrast"]
    A(f"### 4.4 Contrast  (F1={m['f1']:.3f}, Prec={m['precision']:.3f}, Rec={m['recall']:.3f})")
    A(f"")
    A(f"Precision is very high ({m['precision']:.3f}) — when SPIRES predicts contrast status, it")
    A(f"is almost always right. However, recall is {m['recall']:.3f}: FN={m['FN']} cases where")
    A(f"SPIRES returned null even though the gold says WO.")
    A(f"")
    A(f"Root cause: when no contrast keyword appears (e.g., plain X-ray named `Femur Both Lat`),")
    A(f"SPIRES defaults to null instead of inferring WO from context.")
    A(f"")
    fn_con = attr_fn_examples.get("contrast", [])[:8]
    if fn_con:
        A(f"**FN examples (gold=WO/W, SPIRES returned null):**")
        A(f"")
        A(f"| Local name | Gold contrast | LOINC LCN |")
        A(f"|------------|--------------|-----------|")
        for ex in fn_con:
            A(f"| `{ex['name']}` | `{ex['gold']}` | `{ex.get('lcn','')}` |")
    A(f"")

    # --- view ---
    m = spires_metrics["per_attribute"]["view"]
    A(f"### 4.5 View  (F1={m['f1']:.3f})")
    A(f"")
    A(f"View extraction completely fails (F1=0.000). SPIRES extracts views ({m['n_pred']} times)")
    A(f"but they never match the gold ({m['n_gold']} non-null gold values).")
    A(f"The root cause is **vocabulary mismatch**: gold uses Playbook-standardized terms")
    A(f"(`2 views`, `Single view`, `Views`) while SPIRES outputs informal terms")
    A(f"(`Lateral`, `AP`, `3D`). Neither value set is wrong — they use different granularities.")
    A(f"")
    ex_view = [(e["name"], e["gold"].get("view"), e["pred"].get("view"))
               for e in errors if e["has_loinc"]
               and e["gold"].get("view") and e["pred"].get("view")][:8]
    if ex_view:
        A(f"| Local name | Gold view | SPIRES view |")
        A(f"|------------|-----------|-------------|")
        for name, gv, sv in ex_view:
            A(f"| `{name}` | {_fmt_val(gv)} | {_fmt_val(sv)} |")
    A(f"")

    # --- timing ---
    m = spires_metrics["per_attribute"]["timing"]
    A(f"### 4.6 Timing  (F1={m['f1']:.3f})")
    A(f"")
    A(f"Timing fails entirely (F1=0.000). Gold timing values (`wo`, `w`, etc.) appear to be")
    A(f"artefacts of the Playbook's `Rad.Timing` field encoding contrast timing, not temporal")
    A(f"context in the usual sense. SPIRES correctly returns null almost always (only {m['n_pred']}")
    A(f"extractions), but gold has {m['n_gold']} non-null values — leading to FN={m['FN']}.")
    A(f"")

    # --- reason ---
    m = spires_metrics["per_attribute"]["reason"]
    A(f"### 4.7 Reason for Exam  (F1={m['f1']:.3f})")
    A(f"")
    A(f"Reason fails (F1=0.000) due to **SPIRES hallucination**: FP={m['FP']} cases where SPIRES")
    A(f"invents a clinical reason that is not in the local procedure name or the gold.")
    A(f"Gold has only {m['n_gold']} non-null reason values in the Playbook, so this is a rare attribute.")
    A(f"")
    fp_rea = attr_fp_examples.get("reason", [])[:6]
    if fp_rea:
        A(f"**FP examples (SPIRES hallucinated a reason):**")
        A(f"")
        A(f"| Local name | Gold | SPIRES reason |")
        A(f"|------------|------|---------------|")
        for ex in fp_rea:
            A(f"| `{ex['name']}` | {_fmt_val(ex['gold'])} | `{ex['pred']}` |")
    A(f"")

    # ---------------------------------------------------------------
    A(f"---")
    A(f"")
    A(f"## 5. No-LOINC Case Analysis (없음, N={n_no})")
    A(f"")
    A(f"For 없음-labeled samples, SPIRES should ideally return all-null.")
    A(f"Only **{binary_metrics['no_loinc_abstain_correct_rate']:.1%}** ({ncc}/{n_no}) were")
    A(f"correctly abstained. The remaining {n_no - ncc} had at least one spurious attribute.")
    A(f"")
    A(f"**Correctly abstained examples (SPIRES returned all-null):**")
    A(f"")
    for e in abstain_correct[:5]:
        A(f"- `{e['name']}`")
    A(f"")
    A(f"**Hallucination examples (SPIRES extracted attributes for no-LOINC cases):**")
    A(f"")
    if abstain_wrong:
        A(f"| Local name | Spurious extractions |")
        A(f"|------------|----------------------|")
        for e in abstain_wrong[:10]:
            extractions = {k: v["pred"] for k, v in e["mismatches"].items()
                           if v["gold"] is None and v["pred"] is not None}
            if extractions:
                ext_str = ", ".join(f"`{k}`={_fmt_val(v)}" for k, v in extractions.items())
                A(f"| `{e['name']}` | {ext_str} |")
    A(f"")
    A(f"**Pattern**: SPIRES tends to extract `anatomy_focus`, `laterality`, and `guidance_action`")
    A(f"from procedure names that contain anatomic terms (e.g., `PCN Lt` -> laterality=left,")
    A(f"anatomy_focus=kidney) even when the procedure has no standard LOINC imaging code.")
    A(f"")

    # ---------------------------------------------------------------
    A(f"---")
    A(f"")
    A(f"## 6. Fully Correct Predictions (All Attributes Match)")
    A(f"")
    A(f"**{len(correct_examples)} / {n_has} has-LOINC samples** had all 10 attributes correct.")
    A(f"These share a common pattern: **explicit, unambiguous procedure names**.")
    A(f"")
    for e in correct_examples[:10]:
        g = e["gold"]
        parts = [f"modality={g.get('modality')}",
                 f"focus={g.get('anatomy_focus')}",
                 f"laterality={g.get('laterality')}",
                 f"contrast={g.get('contrast')}"]
        parts = [p for p in parts if "None" not in p]
        A(f"- `{e['name']}` -> {', '.join(parts)}")
    A(f"")

    # ---------------------------------------------------------------
    A(f"---")
    A(f"")
    A(f"## 7. Worst-Case Predictions")
    A(f"")
    A(f"Samples with the most attribute mismatches:")
    A(f"")
    A(f"| Local name | Gold LOINC | # Mismatches | Wrong attributes |")
    A(f"|------------|-----------|:------------:|-----------------|")
    for e in bad_examples[:10]:
        wrong = ", ".join(f"`{k}`" for k in e["mismatches"])
        A(f"| `{e['name']}` | `{e['loinc_num']}` | {e['n_mismatches']} | {wrong} |")
    A(f"")

    # ---------------------------------------------------------------
    A(f"---")
    A(f"")
    A(f"## 8. Error Pattern Summary")
    A(f"")
    A(f"| Error Pattern | Count | Root Cause |")
    A(f"|---------------|------:|-----------|")
    A(f"| Modality FN (null when should extract) | {len(attr_fn_examples.get('modality',[]))} | Implicit modality — no standard abbreviation in name |")
    A(f"| Laterality FP (extracted when null gold) | {len(attr_fp_examples.get('laterality',[]))} | Over-assignment of `unspecified` to non-paired structures |")
    A(f"| Anatomy focus mismatch | {len(attr_mismatch_examples.get('anatomy_focus',[]))} | Vocabulary granularity difference (thyroid vs thyroid gland) |")
    A(f"| Contrast FN (defaulted to null) | {len(attr_fn_examples.get('contrast',[]))} | Missing explicit contrast keyword in name (e.g., plain XR) |")
    A(f"| View mismatch | {len(attr_mismatch_examples.get('view',[]))} | Schema uses informal terms; gold uses Playbook-standardized counts |")
    A(f"| Reason FP (hallucinated reason) | {len(attr_fp_examples.get('reason',[]))} | SPIRES invents clinical reasons not present in text |")
    A(f"| No-LOINC hallucination | {n_no - ncc} | Extracts attributes from non-imaging/interventional names |")
    A(f"")
    A(f"---")
    A(f"")
    A(f"## 9. Limitations")
    A(f"")
    A(f"1. **Gold standard imperfection**: The Playbook's `Rad.Timing` field encodes contrast timing")
    A(f"   (`W`, `WO`) rather than temporal context, causing all timing evaluations to fail.")
    A(f"   Some LOINC codes have placeholder modality values (`{{Imaging modality}}`).")
    A(f"")
    A(f"2. **Normalization mismatch**: Anatomy terms like `thyroid gland` vs `thyroid` are treated")
    A(f"   as mismatches despite being semantically equivalent. A fuzzy-match or ontology-based")
    A(f"   comparison (RadLex grounding) would reduce false negatives.")
    A(f"")
    A(f"3. **No grounding**: This experiment evaluates text-level extraction only.")
    A(f"   SPIRES's grounding step (mapping to RadLex RIDs) was skipped, so ontology-level")
    A(f"   equivalence (e.g., `knee` = RID2093) is not leveraged.")
    A(f"")
    A(f"4. **Implicit attributes**: Many attributes are not stated in the local order name and")
    A(f"   require domain knowledge to infer (e.g., `Defecography` -> modality=RF,")
    A(f"   `Infantogram` -> modality=XR). SPIRES cannot infer these without examples.")
    A(f"")
    A(f"5. **Schema prompt sensitivity**: SPIRES prompts are derived directly from the LinkML")
    A(f"   attribute `description` field. Small changes in wording affect extraction behavior.")
    A(f"")
    A(f"6. **Model**: All results use gpt-4o-mini. Larger models (GPT-4o, Claude Opus) may")
    A(f"   produce better results, especially for implicit attributes.")
    A(f"")
    A(f"---")
    A(f"")
    A(f"*Generated by `report_generator.py` — Experiment A, SPIRES parsing-only evaluation*")

    return "\n".join(lines)


def save_report(report_text: str, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"Report saved: {path}")
