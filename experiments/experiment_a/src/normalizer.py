# -*- coding: utf-8 -*-
"""
Attribute normalization utilities for comparing ARKE and SPIRES outputs
against gold standard derived from the LOINC/RSNA Radiology Playbook.
"""

import re

# ---------------------------------------------------------------------------
# Modality normalization
# ---------------------------------------------------------------------------
MODALITY_MAP = {
    # LLM aliases → canonical
    "mri": "MR", "mri-": "MR", "magnetic resonance": "MR",
    "mr": "MR",
    "ct": "CT", "computed tomography": "CT",
    "cta": "CTA", "ct angiography": "CTA", "ct angio": "CTA",
    "mra": "MRA", "mr angiography": "MRA",
    "us": "US", "ultrasound": "US", "sonography": "US",
    "sono": "US", "ultrasonography": "US",
    "xr": "XR", "x-ray": "XR", "radiograph": "XR",
    "plain radiograph": "XR", "plain film": "XR",
    "nm": "NM", "nuclear medicine": "NM",
    "spect": "SPECT", "nm.spect": "SPECT",
    "pet": "PET", "pet/ct": "PET", "pet/mr": "PET",
    "rf": "RF", "fluoroscopy": "RF",
    "mg": "MG", "mammography": "MG", "mammogram": "MG",
    "dxa": "DXA", "dexa": "DXA",
}


def normalize_modality(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower().rstrip("-")
    canonical = MODALITY_MAP.get(v)
    if canonical:
        return canonical
    # Try uppercase first (many LLMs return uppercase)
    return value.strip().upper() if value.strip() else None


# ---------------------------------------------------------------------------
# Anatomy normalization
# ---------------------------------------------------------------------------
ANATOMY_SYNONYMS = {
    # LLM term → Playbook-style canonical (lowercase)
    "brain": "brain",
    "cerebral": "brain",
    "intracranial": "brain",
    "head": "head",
    "skull": "skull",
    "face": "face",
    "orbit": "orbit",
    "eye": "orbit",
    "sella turcica": "sella turcica",
    "pituitary": "pituitary gland",
    "pituitary gland": "pituitary gland",
    "neck": "neck",
    "thyroid": "thyroid gland",
    "thyroid gland": "thyroid gland",
    "parathyroid": "parathyroid gland",
    "chest": "chest",
    "thorax": "chest",
    "lung": "lung",
    "pulmonary": "lung",
    "heart": "heart",
    "cardiac": "heart",
    "aorta": "aorta",
    "coronary": "coronary artery",
    "breast": "breast",
    "abdomen": "abdomen",
    "abdominal": "abdomen",
    "liver": "liver",
    "hepatic": "liver",
    "biliary": "biliary tract",
    "gallbladder": "gallbladder",
    "pancreas": "pancreas",
    "spleen": "spleen",
    "kidney": "kidney",
    "renal": "kidney",
    "adrenal": "adrenal gland",
    "bowel": "bowel",
    "colon": "colon",
    "rectum": "rectum",
    "pelvis": "pelvis",
    "pelvic": "pelvis",
    "uterus": "uterus",
    "ovary": "ovary",
    "prostate": "prostate",
    "bladder": "bladder",
    "spine": "spine",
    "spinal cord": "spinal cord",
    "cervical spine": "cervical spine",
    "thoracic spine": "thoracic spine",
    "lumbar spine": "lumbar spine",
    "sacrum": "sacrum",
    "shoulder": "shoulder",
    "humerus": "humerus",
    "elbow": "elbow",
    "forearm": "forearm",
    "wrist": "wrist",
    "hand": "hand",
    "finger": "finger",
    "thumb": "thumb",
    "hip": "hip",
    "femur": "femur",
    "thigh": "femur",
    "knee": "knee",
    "lower leg": "lower leg",
    "tibia": "tibia",
    "fibula": "fibula",
    "ankle": "ankle",
    "foot": "foot",
    "toe": "toe",
    "upper extremity": "upper extremity",
    "lower extremity": "lower extremity",
    "extremity": "extremity",
    "bone": "bone",
    "bones": "bone",
    "joint": "joint",
    "vessel": "vessel",
    "vascular": "vessel",
    "lymph node": "lymph node",
    "soft tissue": "soft tissue",
    "whole body": "whole body",
    "body": "whole body",
    "unspecified body region": "unspecified body region",
}

# Suffixes to strip before lookup
_STRIP_SUFFIXES = [" joint", " gland", " region", " structure"]


def normalize_anatomy(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    # Direct synonym lookup
    if v in ANATOMY_SYNONYMS:
        return ANATOMY_SYNONYMS[v]
    # Strip common suffixes and retry
    for suffix in _STRIP_SUFFIXES:
        if v.endswith(suffix):
            stripped = v[: -len(suffix)]
            if stripped in ANATOMY_SYNONYMS:
                return ANATOMY_SYNONYMS[stripped]
    return v  # Return as-is (lowercased) if no mapping found


# ---------------------------------------------------------------------------
# Laterality normalization
# ---------------------------------------------------------------------------
LATERALITY_MAP = {
    "left": "left", "lt": "left", "l": "left",
    "right": "right", "rt": "right", "r": "right",
    "bilateral": "bilateral", "both": "bilateral", "bil": "bilateral",
    "b": "bilateral",
    "unspecified": "unspecified", "n/a": None, "na": None, "none": None,
}


def normalize_laterality(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    return LATERALITY_MAP.get(v, v)


# ---------------------------------------------------------------------------
# Contrast normalization
# ---------------------------------------------------------------------------
CONTRAST_MAP = {
    "w": "W", "with": "W", "with contrast": "W", "post": "W",
    "wo": "WO", "without": "WO", "without contrast": "WO",
    "non-contrast": "WO", "noncontrast": "WO", "plain": "WO",
    "w_wo": "W_WO", "w and wo": "W_WO", "w&wo": "W_WO",
    "with and without": "W_WO", "before and after": "W_WO",
}


def normalize_contrast(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower().replace("-", "_")
    return CONTRAST_MAP.get(v, value.strip().upper())


# ---------------------------------------------------------------------------
# View normalization
# ---------------------------------------------------------------------------
VIEW_SYNONYMS = {
    "ap": "AP",
    "anteroposterior": "AP",
    "pa": "PA",
    "posteroanterior": "PA",
    "lateral": "Lateral",
    "lat": "Lateral",
    "oblique": "Oblique",
    "obl": "Oblique",
    "ap and lateral": "AP and Lateral",
    "ap lateral": "AP and Lateral",
    "single view": "Single view",
    "one view": "Single view",
    "2 views": "2 views",
    "two views": "2 views",
    "3 views": "3 views",
    "three views": "3 views",
    "4 views": "4 views",
    "views": "Views",
    "crosstable lateral": "crosstable lateral",
    "cross table lateral": "crosstable lateral",
}


def normalize_view(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    # Count-based normalization: "2 views" etc.
    m = re.match(r"(\d+)\s*views?", v)
    if m:
        return f"{m.group(1)} views"
    return VIEW_SYNONYMS.get(v, value.strip())


# ---------------------------------------------------------------------------
# Guidance action normalization
# ---------------------------------------------------------------------------
GUIDANCE_ACTION_MAP = {
    "biopsy": "biopsy",
    "core biopsy": "biopsy",
    "core needle biopsy": "biopsy",
    "fine needle aspiration": "aspiration",
    "fna": "aspiration",
    "aspiration": "aspiration",
    "drainage": "drainage",
    "injection": "injection",
    "nerve block": "nerve block",
    "block": "nerve block",
    "ablation": "ablation",
    "embolization": "embolization",
    "placement": "placement",
    "stent placement": "placement",
    "catheter placement": "placement",
    "localization": "localization",
    "needle localization": "localization",
    "vertebroplasty": "vertebroplasty",
}


def normalize_guidance(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    return GUIDANCE_ACTION_MAP.get(v, v)


# ---------------------------------------------------------------------------
# Main normalization dispatcher
# ---------------------------------------------------------------------------
NORMALIZERS = {
    "modality":        normalize_modality,
    "anatomy_focus":   normalize_anatomy,
    "anatomy_region":  normalize_anatomy,
    "laterality":      normalize_laterality,
    "contrast":        normalize_contrast,
    "view":            normalize_view,
    "guidance_action": normalize_guidance,
    "guidance_object": lambda x: x.strip().lower() if x else None,
    "timing":          lambda x: x.strip().lower() if x else None,
    "reason":          lambda x: x.strip().lower() if x else None,
}

EVAL_ATTRIBUTES = [
    "modality",
    "anatomy_focus",
    "anatomy_region",
    "laterality",
    "contrast",
    "view",
    "guidance_action",
    "guidance_object",
    "timing",
    "reason",
]


def normalize_record(record: dict) -> dict:
    """Apply per-attribute normalization to a prediction or gold record."""
    out = {}
    for attr in EVAL_ATTRIBUTES:
        fn = NORMALIZERS.get(attr, lambda x: x)
        out[attr] = fn(record.get(attr))
    return out
