# -*- coding: utf-8 -*-
"""
Gold standard attribute extraction from LOINC/RSNA Radiology Playbook CSV.

For each labeled LOINC code in the gold reference file, derives structured
attributes (modality, anatomy, laterality, contrast, view, guidance, etc.)
by joining with the Playbook CSV.
"""

import re
import json
from pathlib import Path
import pandas as pd

PLAYBOOK_CSV = Path(
    "C:/Projects/llm_loinc/SPIRES/playbook/AccessoryFiles"
    "/LoincRsnaRadiologyPlaybook/LoincRsnaRadiologyPlaybook.csv"
)
GOLD_REF_XLSX = Path(
    "C:/Projects/llm_loinc/SPIRES/gold_references/snuh_250926.xlsx"
)
RESULTS_DIR = Path(
    "C:/Projects/llm_loinc/SPIRES/experiments/experiment_a/results"
)

# Maps Playbook PartTypeName → our internal key
PART_TYPE_MAP = {
    "Rad.Modality.Modality Type":             "modality",
    "Rad.Modality.Modality Subtype":          "modality_subtype",
    "Rad.Anatomic Location.Region Imaged":    "anatomy_region",
    "Rad.Anatomic Location.Imaging Focus":    "anatomy_focus",
    "Rad.Anatomic Location.Laterality":       "laterality",
    "Rad.View.Aggregation":                   "view_aggregation",
    "Rad.View.View Type":                     "view_type",
    "Rad.Pharmaceutical.Route":               "pharm_route",
    "Rad.Pharmaceutical.Substance Given":     "pharm_substance",
    "Rad.Guidance for.Action":                "guidance_action",
    "Rad.Guidance for.Object":                "guidance_object",
    "Rad.Guidance for.Approach":              "guidance_approach",
    "Rad.Guidance for.Presence":              "guidance_presence",
    "Rad.Timing":                             "timing",
    "Rad.Reason for Exam":                    "reason",
    "Rad.Maneuver.Maneuver Type":             "maneuver",
    "Rad.Subject":                            "subject",
}

# Multivalued attributes (can have multiple PartNames per LOINC code)
MULTIVALUED = {
    "anatomy_region", "anatomy_focus", "view_aggregation", "view_type",
    "pharm_route", "pharm_substance", "guidance_action", "guidance_object",
    "guidance_approach",
}


def parse_contrast_from_lcn(long_common_name: str) -> str:
    """
    Infer W/WO/W_WO from the LOINC Long Common Name.
    LOINC naming convention is very systematic about this.
    """
    name = long_common_name.upper()
    if re.search(r"\bW AND WO\b", name) or re.search(r"\bW\s*&\s*WO\b", name):
        return "W_WO"
    # "WO contrast" must come before "W contrast" check
    if re.search(r"\bWO\s+CONTRAST\b", name) or re.search(r"^[^W]*\bWO\b", name):
        return "WO"
    if re.search(r"\bW\s+CONTRAST\b", name):
        return "W"
    # Route abbreviations without explicit W/WO → with contrast
    if re.search(r"\b(IV|IT|IA|SC|IN|PO|PR)\b", name):
        return "W"
    return "WO"


def build_gold_attributes(loinc_num: str, long_common_name: str,
                           playbook_df: pd.DataFrame) -> dict:
    """
    Build a gold attribute dict for one LOINC code using Playbook data.
    """
    rows = playbook_df[playbook_df["LoincNumber"] == loinc_num]

    raw = {}
    for _, row in rows.iterrows():
        pt = row.get("PartTypeName")
        pn = row.get("PartName")
        if pd.isna(pt) or pd.isna(pn):
            continue
        key = PART_TYPE_MAP.get(pt)
        if key is None:
            continue
        if key in MULTIVALUED:
            raw.setdefault(key, [])
            if pn not in raw[key]:
                raw[key].append(pn)
        else:
            raw[key] = pn

    # --- Normalize laterality ---
    lat = raw.get("laterality")
    if lat:
        lat_lower = lat.lower()
        if "right" in lat_lower:
            lat = "right"
        elif "left" in lat_lower:
            lat = "left"
        elif "bilateral" in lat_lower:
            lat = "bilateral"
        else:
            lat = "unspecified"
    else:
        lat = None

    # --- Derive contrast ---
    contrast = parse_contrast_from_lcn(long_common_name)

    # --- Derive canonical anatomy ---
    # Focus is more specific; fall back to region
    foci = raw.get("anatomy_focus", [])
    regions = raw.get("anatomy_region", [])
    anatomy_focus = foci[0].lower() if foci else None
    anatomy_region = regions[0].lower() if regions else None

    # --- View: combine aggregation + type ---
    view_agg = raw.get("view_aggregation", [])
    view_type = raw.get("view_type", [])
    view_parts = view_agg + [v for v in view_type if v not in view_agg]
    view = "; ".join(view_parts).lower() if view_parts else None

    # --- Guidance ---
    g_actions = raw.get("guidance_action", [])
    g_objects = raw.get("guidance_object", [])
    guidance_action = "; ".join(g_actions).lower() if g_actions else None
    guidance_object = "; ".join(g_objects).lower() if g_objects else None

    # --- Timing / Reason ---
    timing = raw.get("timing", "").lower() or None
    reason = raw.get("reason", "").lower() or None

    modality = raw.get("modality")
    # Playbook placeholder values → treat as null
    if modality and (modality.startswith("{") or modality.startswith("(")):
        modality = None

    # --- Collect raw RIDs directly from Playbook rows (ground truth) ---
    # These are the authoritative RadLex identifiers for each axis.
    def _first_rid(part_type):
        sub = rows[rows["PartTypeName"] == part_type]["RID"].dropna()
        sub = sub[~sub.str.startswith("{")]
        return sub.iloc[0] if len(sub) > 0 else None

    return {
        "loinc_num":          loinc_num,
        "long_common_name":   long_common_name,
        # Text values (for display / fallback)
        "modality":           modality,
        "anatomy_focus":      anatomy_focus,
        "anatomy_region":     anatomy_region,
        "laterality":         lat,
        "contrast":           contrast,
        "view":               view,
        "guidance_action":    guidance_action,
        "guidance_object":    guidance_object,
        "timing":             timing,
        "reason":             reason,
        # RadLex RIDs (authoritative ground truth for grounded evaluation)
        "rid_modality":       _first_rid("Rad.Modality.Modality Type"),
        "rid_anatomy_focus":  _first_rid("Rad.Anatomic Location.Imaging Focus"),
        "rid_anatomy_region": _first_rid("Rad.Anatomic Location.Region Imaged"),
        "rid_laterality":     _first_rid("Rad.Anatomic Location.Laterality"),
        "rid_guidance_action":_first_rid("Rad.Guidance for.Action"),
        "rid_guidance_object":_first_rid("Rad.Guidance for.Object"),
    }


def parse_label(label_str: str):
    """
    Parse 'XXXXX-X - Long Common Name' → (loinc_num, long_common_name).
    Returns (None, None) for '없음' or malformed strings.
    """
    if not isinstance(label_str, str):
        return None, None
    label_str = label_str.strip()
    if label_str in ("없음", "건너뜀", ""):
        return None, None
    # Pattern: "12345-6 - Some Name"
    m = re.match(r"^(\d+[-‐]\d+)\s+-\s+(.+)$", label_str)
    if m:
        return m.group(1), m.group(2).strip()
    return None, None


def prepare_gold_standard() -> list[dict]:
    """
    Load gold reference XLSX, join with Playbook, return list of gold records.
    Only includes rows with valid (non-없음) LOINC labels.
    """
    print("Loading gold reference XLSX...")
    gold_df = pd.read_excel(GOLD_REF_XLSX)
    # Columns: '(원본) 오더명', '필터링', 'label'
    order_col = "(원본) 오더명"

    print("Loading LOINC/RSNA Playbook...")
    playbook_df = pd.read_csv(PLAYBOOK_CSV, header=1, low_memory=False)
    playbook_df = playbook_df[playbook_df["LoincNumber"].notna()].copy()

    NULL_ATTRS = {
        "loinc_num": None, "long_common_name": None,
        "modality": None, "anatomy_focus": None, "anatomy_region": None,
        "laterality": None, "contrast": None, "view": None,
        "guidance_action": None, "guidance_object": None,
        "timing": None, "reason": None,
    }

    records = []
    n_valid, n_none = 0, 0
    for _, row in gold_df.iterrows():
        local_name = str(row[order_col]).strip()
        label = row.get("label", "")
        loinc_num, lcn = parse_label(label)

        if loinc_num is None:
            # No LOINC match — gold is all-null
            records.append({
                "local_name": local_name,
                "has_loinc": False,
                "gold": dict(NULL_ATTRS),
            })
            n_none += 1
        else:
            gold_attrs = build_gold_attributes(loinc_num, lcn, playbook_df)
            records.append({
                "local_name": local_name,
                "has_loinc": True,
                "gold": gold_attrs,
            })
            n_valid += 1

    print(f"  Total: {len(records)} (has LOINC: {n_valid}, no LOINC: {n_none})")
    return records


def save_gold_standard(records: list[dict]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "gold_standard.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"Saved gold standard: {out_path}")
    return out_path


if __name__ == "__main__":
    records = prepare_gold_standard()
    save_gold_standard(records)
    # Quick preview
    for r in records[:3]:
        print(f"\n[{r['local_name']}]")
        g = r["gold"]
        for k, v in g.items():
            if v:
                print(f"  {k}: {v}")
