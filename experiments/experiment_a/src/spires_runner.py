# -*- coding: utf-8 -*-
"""
SPIRES Runner: ontogpt SPIRESEngine-based attribute extraction.

Uses the radiology_procedure.yaml LinkML schema with ontogpt's SPIRES
(Structured Prompt Interrogation and Recursive Extraction from Schemas)
engine. Extracts attributes recursively according to schema definition.
"""

import json
import logging
import os
import time
from dataclasses import asdict
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(
    "C:/Projects/llm_loinc/SPIRES/experiments/experiment_a/schema/radiology_procedure.yaml"
)
RESULTS_DIR = Path(
    "C:/Projects/llm_loinc/SPIRES/experiments/experiment_a/results"
)


def _extraction_to_dict(extracted_object) -> dict:
    """Convert ontogpt extraction result pydantic object to plain dict."""
    if extracted_object is None:
        return {}
    try:
        # Pydantic v2
        raw = extracted_object.model_dump()
    except AttributeError:
        try:
            raw = extracted_object.dict()
        except AttributeError:
            raw = asdict(extracted_object) if hasattr(extracted_object, '__dataclass_fields__') else {}

    # Keep only our eval attributes
    attrs = [
        "modality", "anatomy_focus", "anatomy_region",
        "laterality", "contrast", "view",
        "guidance_action", "guidance_object",
        "timing", "reason",
    ]
    result = {}
    for attr in attrs:
        val = raw.get(attr)
        # ontogpt may return 'None' string or empty list for null fields
        if val in (None, [], "", "None", "N/A", "null"):
            result[attr] = None
        elif isinstance(val, list):
            result[attr] = "; ".join(str(v) for v in val if v) or None
        else:
            result[attr] = str(val).strip() or None
    return result


class SPIRESRunner:
    """SPIRES-based extraction using ontogpt SPIRESEngine."""

    def __init__(self, model: str = "gpt-4o-mini", api_key: str = None):
        self.model = model
        self.api_key = api_key
        self._engine = None
        self._template_details = None

    def _init_engine(self):
        """Lazy initialization of SPIRESEngine (heavy import)."""
        if self._engine is not None:
            return

        if self.api_key:
            os.environ["OPENAI_API_KEY"] = self.api_key

        from ontogpt.engines.spires_engine import SPIRESEngine
        from ontogpt.io.template_loader import get_template_details

        logger.info(f"Loading SPIRES template from {SCHEMA_PATH}")
        self._template_details = get_template_details(str(SCHEMA_PATH))

        self._engine = SPIRESEngine(
            template_details=self._template_details,
            model=self.model,
            temperature=0.0,
        )
        logger.info(f"SPIRES engine initialized (model={self.model})")

    def parse(self, procedure_name: str) -> dict:
        """
        Extract structured attributes from a single procedure name via SPIRES.
        """
        self._init_engine()
        try:
            result = self._engine.extract_from_text(text=procedure_name)
            return _extraction_to_dict(result.extracted_object)
        except Exception as e:
            logger.error(f"SPIRES extraction failed for '{procedure_name}': {e}")
            return {k: None for k in [
                "modality", "anatomy_focus", "anatomy_region",
                "laterality", "contrast", "view",
                "guidance_action", "guidance_object",
                "timing", "reason",
            ]}

    def parse_batch(self, records: list[dict],
                    cache_path: Path = None,
                    delay: float = 0.5) -> list[dict]:
        """
        Parse a list of records. Saves intermediate results for resumption.
        """
        done = {}
        if cache_path and cache_path.exists():
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            done = {r["local_name"]: r["spires"] for r in cached}
            print(f"  Loaded {len(done)} cached SPIRES results from {cache_path}")

        results = []
        total = len(records)
        for i, rec in enumerate(records):
            name = rec["local_name"]
            if name in done:
                results.append({"local_name": name, "spires": done[name]})
                continue

            print(f"  SPIRES [{i+1}/{total}] {name[:60].encode('ascii','replace').decode()}")
            attrs = self.parse(name)
            results.append({"local_name": name, "spires": attrs})
            done[name] = attrs

            if cache_path:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)

            time.sleep(delay)

        return results


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv("C:/Projects/llm_loinc/SPIRES/.env")

    runner = SPIRESRunner(api_key=os.environ.get("OPENAI_API_KEY"))
    test_cases = [
        "MRI Brain-RLS (noncontrast)",
        "CT Hip Trauma + 3D (noncontrast)",
        "SONO Research Gun Biopsy - Breast",
        "Foot & Ankle Rt Lat (DF)",
    ]
    for name in test_cases:
        result = runner.parse(name)
        print(f"\n[{name}]")
        for k, v in result.items():
            if v is not None:
                print(f"  {k}: {v}")
