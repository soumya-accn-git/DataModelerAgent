"""
Step 4b — OWL/SHACL rules engine
Applies all inference and validation rules including Rule R6 (filter inference).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from src.knowledge.rules import apply_all_rules


def apply_owl_rules(
    entities: list[dict],
    relationships: list[dict],
    on_log=None,
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:

    def log(msg):
        if on_log: on_log(msg)

    log("Applying OWL Rules R1–R6 and SHACL validation…")
    entities, relationships, inferred, violations = apply_all_rules(entities, relationships)

    filter_inferred = [e for e in inferred if e.get("inferred_from_filter")]
    report_inferred = [e for e in inferred if not e.get("inferred_from_filter")]

    log(
        f"R6: {len(filter_inferred)} dimensions from filters/prompts. "
        f"R1/R2: {len(report_inferred)} from reports. "
        f"SHACL: {len(violations)} issues."
    )

    return entities, relationships, inferred, violations
