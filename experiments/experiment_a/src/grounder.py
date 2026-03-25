# -*- coding: utf-8 -*-
"""
Playbook-based RadLex grounding.

Builds lookup tables from the LOINC/RSNA Radiology Playbook CSV:
  PartName (text) -> RID  (per PartTypeName axis)

Used to ground both:
  - Gold standard attributes (already have RIDs in Playbook)
  - SPIRES extracted text values (need lookup by extracted text)

Grounding makes evaluation ontology-level rather than text-level:
  gold="Thyroid gland" (RID7578), SPIRES="thyroid" -> ground to RID7578 -> MATCH
"""

from __future__ import annotations
from pathlib import Path
import pandas as pd

PLAYBOOK_CSV = Path(
    "C:/Projects/llm_loinc/SPIRES/playbook/AccessoryFiles"
    "/LoincRsnaRadiologyPlaybook/LoincRsnaRadiologyPlaybook.csv"
)

# Maps our attribute names -> Playbook PartTypeName
ATTR_TO_PART_TYPE = {
    "modality":        "Rad.Modality.Modality Type",
    "modality_subtype":"Rad.Modality.Modality Subtype",
    "anatomy_focus":   "Rad.Anatomic Location.Imaging Focus",
    "anatomy_region":  "Rad.Anatomic Location.Region Imaged",
    "laterality":      "Rad.Anatomic Location.Laterality",
    "view":            "Rad.View.Aggregation",
    "view_type":       "Rad.View.View Type",
    "guidance_action": "Rad.Guidance for.Action",
    "guidance_object": "Rad.Guidance for.Object",
    "guidance_approach":"Rad.Guidance for.Approach",
    "timing":          "Rad.Timing",
    "reason":          "Rad.Reason for Exam",
}

# Attributes where grounding is applied in evaluation
GROUNDABLE_ATTRS = [
    "modality",
    "anatomy_focus",
    "anatomy_region",
    "laterality",
    "guidance_action",
    "guidance_object",
]


class PlaybookGrounder:
    """
    Lookup-based grounding from Playbook PartName -> RadLex RID.

    lookup[attr][text_lower] = RID  (e.g. lookup["modality"]["ct"] = "RID10321")
    rid_to_name[RID] = PreferredName
    rid_to_partname[RID] = canonical PartName from Playbook
    """

    def __init__(self):
        self.lookup: dict[str, dict[str, str]] = {}   # attr -> {text_lower -> RID}
        self.rid_to_name: dict[str, str] = {}          # RID -> PreferredName
        self.rid_to_partname: dict[str, str] = {}      # RID -> PartName (first seen)
        self._load()

    def _load(self):
        df = pd.read_csv(PLAYBOOK_CSV, header=1, low_memory=False)
        df = df[df["RID"].notna() & df["PartName"].notna()].copy()
        df["PartName"] = df["PartName"].astype(str).str.strip()
        df["RID"] = df["RID"].astype(str).str.strip()
        df["PreferredName"] = df["PreferredName"].fillna("").astype(str).str.strip()

        for attr, part_type in ATTR_TO_PART_TYPE.items():
            sub = df[df["PartTypeName"] == part_type]
            self.lookup[attr] = {}
            for _, row in sub.drop_duplicates("PartName").iterrows():
                pname = row["PartName"]
                rid   = row["RID"]
                pref  = row["PreferredName"]
                # Skip Playbook placeholder values
                if pname.startswith("{") or pname.startswith("("):
                    continue
                key = pname.lower()
                self.lookup[attr][key] = rid
                if rid not in self.rid_to_name:
                    self.rid_to_name[rid] = pref or pname
                if rid not in self.rid_to_partname:
                    self.rid_to_partname[rid] = pname

        # Also register stripped/simplified versions of PartNames as aliases
        # e.g. "Thyroid gland" -> also register "thyroid" -> same RID
        _strip_suffixes = [" gland", " organ", " joint", " region",
                           " structure", " vessels", " vessel", " cord",
                           " bones", " bone", " system"]
        for attr in list(self.lookup.keys()):
            additions = {}
            for text_lower, rid in list(self.lookup[attr].items()):
                for suffix in _strip_suffixes:
                    if text_lower.endswith(suffix):
                        stripped = text_lower[: -len(suffix)]
                        if stripped and stripped not in self.lookup[attr]:
                            additions[stripped] = rid
                # Also register without common anatomic qualifiers
                # e.g. "left breast" and "breast" -> same RID (if present)
            self.lookup[attr].update(additions)

        # Extra aliases for common LLM outputs that don't match PartName exactly
        _modality_aliases = {
            "mr":          "RID10312",   # same as "MR"
            "mri":         "RID10312",
            "ct":          "RID10321",
            "cta":         "RID10321",   # CT angiography still CT modality
            "mra":         "RID10312",   # MR angiography still MR
            "x-ray":       "RID10345",
            "xr":          "RID10345",
            "radiograph":  "RID10345",
            "us":          "RID10326",
            "ultrasound":  "RID10326",
            "sono":        "RID10326",
            "sonography":  "RID10326",
            "nm":          "RID10330",
            "nuclear medicine": "RID10330",
            "rf":          "RID10361",
            "fluoroscopy": "RID10361",
            "pet":         "RID10337",
            "pet/ct":      "RID10341",
            "pt+ct":       "RID10341",
            "mg":          "RID10357",
            "mammography": "RID10357",
            "dxa":         "RID10363",
            "dexa":        "RID10363",
            "spect":       "RID10330",   # NM subtype
        }
        for alias, rid in _modality_aliases.items():
            if alias not in self.lookup.get("modality", {}):
                self.lookup.setdefault("modality", {})[alias] = rid

        # Laterality aliases
        _lat_aliases = {
            "left":        None,   # will be found via PartName lookup
            "right":       None,
            "bilateral":   None,
            "rt":          None,
            "lt":          None,
        }
        for alias in list(self.lookup.get("laterality", {}).keys()):
            pass  # already loaded

        print(f"[Grounder] Loaded lookup tables for {len(self.lookup)} attributes, "
              f"{sum(len(v) for v in self.lookup.values())} total entries, "
              f"{len(self.rid_to_name)} unique RIDs.")

    _QUERY_STRIP = [" joint", " gland", " organ", " region",
                    " structure", " vessels", " vessel", " cord",
                    " bones", " bone", " system"]

    def ground(self, attr: str, text: str | None) -> str | None:
        """
        Ground a text value for an attribute to a RadLex RID.
        Returns RID string (e.g. 'RID10321') or None if not groundable.
        Applies suffix stripping to handle LLM output variations.
        """
        if not text:
            return None
        lut = self.lookup.get(attr, {})
        key = text.strip().lower()
        # Direct lookup
        if key in lut:
            return lut[key]
        # Try stripping common qualifiers from the query
        for suffix in self._QUERY_STRIP:
            if key.endswith(suffix):
                stripped = key[: -len(suffix)]
                if stripped in lut:
                    return lut[stripped]
        return None

    def ground_record(self, record: dict) -> dict:
        """
        Ground all groundable attributes in a record.
        Returns a new dict with {attr: RID} for groundable attrs (None if failed).
        """
        out = {}
        for attr in GROUNDABLE_ATTRS:
            val = record.get(attr)
            rid = self.ground(attr, val)
            out[attr] = rid
        return out

    def rid_label(self, rid: str | None) -> str:
        """Human-readable label for a RID."""
        if not rid:
            return "null"
        name = self.rid_to_name.get(rid, "")
        pname = self.rid_to_partname.get(rid, "")
        return f"{rid} ({pname or name})"


# Singleton — load once
_grounder: PlaybookGrounder | None = None


def get_grounder() -> PlaybookGrounder:
    global _grounder
    if _grounder is None:
        _grounder = PlaybookGrounder()
    return _grounder


if __name__ == "__main__":
    g = get_grounder()
    tests = [
        ("modality",      "MR"),
        ("modality",      "mri"),
        ("modality",      "CT"),
        ("modality",      "CTA"),
        ("modality",      "US"),
        ("modality",      "Sono"),
        ("anatomy_focus", "Thyroid gland"),
        ("anatomy_focus", "thyroid"),        # LLM output — won't match!
        ("anatomy_focus", "Brain"),
        ("anatomy_focus", "Knee"),
        ("anatomy_region","Chest"),
        ("laterality",    "Left"),
        ("laterality",    "right"),
        ("guidance_action","Biopsy"),
    ]
    print("\nGrounding tests:")
    for attr, text in tests:
        rid = g.ground(attr, text)
        label = g.rid_label(rid)
        status = "OK" if rid else "FAIL"
        print(f"  [{status}] {attr}={text!r:25} -> {label}")
