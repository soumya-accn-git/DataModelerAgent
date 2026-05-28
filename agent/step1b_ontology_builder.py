"""
Step 1b — Dynamic Ontology Builder

Reads the BRD text and:
1. Extracts domain-specific concepts, vocabulary, and business rules
2. Generates a domain OWL ontology (Turtle/N3 format)
3. Generates SHACL shapes for entity validation
4. Updates the SKILL.md with BRD-specific guardrails
5. Writes all outputs to ontology/generated/ folder

This runs BEFORE entity extraction so all subsequent steps use
BRD-specific rules rather than generic ones.
"""

import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from agent.ollama_client import chat, extract_json

GENERATED_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "ontology", "generated"
)
SKILL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "skills", "SKILL.md"
)
BASE_SKILL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "skills", "SKILL_BASE.md"
)

os.makedirs(GENERATED_DIR, exist_ok=True)

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_DOMAIN = """You are a senior ontology engineer. Analyse a Business Requirements
Document and extract the domain vocabulary needed to build an OWL ontology and SHACL shapes.

Respond ONLY with valid JSON, no explanation, no markdown."""

USER_DOMAIN = """Analyse this BRD and extract the domain ontology vocabulary.

Return a JSON object with these keys:

"domain_name": short name for this business domain (e.g. "RetailBanking", "ConsumerGoods")
"domain_description": one sentence describing the business domain

"dimension_concepts": list of objects — each a candidate Dimension entity:
  {{"name": "CustomerDimension", "label": "Customer", "description": "...", "attributes": [...], "source": "section name"}}

"fact_concepts": list of objects — each a candidate Fact entity:
  {{"name": "SaleFact", "label": "Sale", "description": "...", "metrics": ["amount","quantity"], "source": "section name"}}

"reference_concepts": list of objects — each a candidate Reference/lookup entity:
  {{"name": "ProductCategory", "label": "Product Category", "description": "...", "source": "section name"}}

"forbidden_patterns": list of strings — patterns found in this BRD that should be
  rejected as entities (report names, dashboard names, filter names, metric names).
  Example: ["ConsumerSpendingReport", "CMODashboard", "Top10Filter"]

"domain_relationships": list of objects — key relationships specific to this domain:
  {{"from": "CustomerDimension", "to": "SaleFact", "label": "makes", "cardinality": "1:N"}}

"key_metrics": list of strings — measurable KPIs/metrics (these become attributes of Fact entities, NOT entities themselves)
  Example: ["TotalRevenue", "UnitsSold", "AverageOrderValue"]

"filters_and_prompts": list of objects — filters/prompts found in the BRD with their implied dimension:
  {{"filter_name": "RegionFilter", "implied_dimension": "GeographyDimension"}}

BRD TEXT:
---
{brd_text}
---
JSON:"""


# ── OWL Turtle generator ──────────────────────────────────────────────────────

def _generate_owl(domain: dict) -> str:
    """Generate an OWL ontology in Turtle format from the domain vocabulary."""
    domain_name = domain.get("domain_name", "BusinessDomain")
    domain_desc = domain.get("domain_description", "")

    lines = [
        f"@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        f"@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        f"@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        f"@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        f"@prefix sh: <http://www.w3.org/ns/shacl#> .",
        f"@prefix cdm: <https://example.org/cdm/{domain_name}#> .",
        f"@prefix schema: <https://schema.org/> .",
        f"",
        f"# ── Ontology declaration ────────────────────────────────────────────────────",
        f"cdm:{domain_name}Ontology",
        f"    a owl:Ontology ;",
        f'    rdfs:label "{domain_name} Conceptual Data Model Ontology" ;',
        f'    rdfs:comment "{domain_desc}" .',
        f"",
        f"# ── Base classes ─────────────────────────────────────────────────────────────",
        f"cdm:DimensionEntity a owl:Class ;",
        f'    rdfs:label "Dimension Entity" ;',
        f'    rdfs:comment "A descriptive axis used to slice and filter facts." .',
        f"",
        f"cdm:FactEntity a owl:Class ;",
        f'    rdfs:label "Fact Entity" ;',
        f'    rdfs:comment "A measurable business event or transaction." .',
        f"",
        f"cdm:ReferenceEntity a owl:Class ;",
        f'    rdfs:label "Reference Entity" ;',
        f'    rdfs:comment "A lookup or classification table." .',
        f"",
        f"cdm:BridgeEntity a owl:Class ;",
        f'    rdfs:label "Bridge Entity" ;',
        f'    rdfs:comment "Resolves M:N between two dimensions." .',
        f"",
    ]

    # Dimension classes
    if domain.get("dimension_concepts"):
        lines.append("# ── Dimension classes ────────────────────────────────────────────────────────")
        for d in domain["dimension_concepts"]:
            name = d.get("name","").strip()
            if not name: continue
            label = d.get("label", name)
            desc  = d.get("description","").replace('"',"'")
            lines += [
                f"cdm:{name} a owl:Class ;",
                f"    rdfs:subClassOf cdm:DimensionEntity ;",
                f'    rdfs:label "{label}" ;',
                f'    rdfs:comment "{desc}" .',
                f"",
            ]
            for attr in d.get("attributes", [])[:5]:
                attr_clean = re.sub(r'[^A-Za-z0-9]', '', attr)
                lines += [
                    f"cdm:{name}_{attr_clean} a owl:DatatypeProperty ;",
                    f"    rdfs:domain cdm:{name} ;",
                    f"    rdfs:range xsd:string ;",
                    f'    rdfs:label "{attr}" .',
                    f"",
                ]

    # Fact classes
    if domain.get("fact_concepts"):
        lines.append("# ── Fact classes ─────────────────────────────────────────────────────────────")
        for f in domain["fact_concepts"]:
            name = f.get("name","").strip()
            if not name: continue
            label = f.get("label", name)
            desc  = f.get("description","").replace('"',"'")
            lines += [
                f"cdm:{name} a owl:Class ;",
                f"    rdfs:subClassOf cdm:FactEntity ;",
                f'    rdfs:label "{label}" ;',
                f'    rdfs:comment "{desc}" .',
                f"",
            ]
            for metric in f.get("metrics", [])[:5]:
                metric_clean = re.sub(r'[^A-Za-z0-9]', '', metric)
                lines += [
                    f"cdm:{name}_{metric_clean} a owl:DatatypeProperty ;",
                    f"    rdfs:domain cdm:{name} ;",
                    f"    rdfs:range xsd:decimal ;",
                    f'    rdfs:label "{metric}" .',
                    f"",
                ]

    # Reference classes
    if domain.get("reference_concepts"):
        lines.append("# ── Reference classes ────────────────────────────────────────────────────────")
        for r in domain["reference_concepts"]:
            name = r.get("name","").strip()
            if not name: continue
            label = r.get("label", name)
            desc  = r.get("description","").replace('"',"'")
            lines += [
                f"cdm:{name} a owl:Class ;",
                f"    rdfs:subClassOf cdm:ReferenceEntity ;",
                f'    rdfs:label "{label}" ;',
                f'    rdfs:comment "{desc}" .',
                f"",
            ]

    # Object properties (relationships)
    if domain.get("domain_relationships"):
        lines.append("# ── Object properties (relationships) ───────────────────────────────────────")
        for rel in domain["domain_relationships"]:
            from_e = rel.get("from","").strip()
            to_e   = rel.get("to","").strip()
            label  = rel.get("label","relatesTo")
            prop_name = re.sub(r'[^A-Za-z0-9]', '', label)
            if not from_e or not to_e: continue
            lines += [
                f"cdm:{prop_name} a owl:ObjectProperty ;",
                f"    rdfs:domain cdm:{from_e} ;",
                f"    rdfs:range cdm:{to_e} ;",
                f'    rdfs:label "{label}" .',
                f"",
            ]

    return "\n".join(lines)


# ── SHACL shapes generator ────────────────────────────────────────────────────

def _generate_shacl(domain: dict) -> str:
    """Generate SHACL node shapes for all domain entities."""
    domain_name = domain.get("domain_name", "BusinessDomain")

    lines = [
        f"@prefix sh: <http://www.w3.org/ns/shacl#> .",
        f"@prefix cdm: <https://example.org/cdm/{domain_name}#> .",
        f"@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        f"@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        f"",
        f"# ── SHACL Shapes for {domain_name} CDM ─────────────────────────────────────",
        f"",
        f"# Global entity name pattern shape",
        f"cdm:EntityNameShape a sh:NodeShape ;",
        f"    sh:targetClass cdm:DimensionEntity, cdm:FactEntity, cdm:ReferenceEntity ;",
        f"    sh:property [",
        f"        sh:path cdm:name ;",
        f"        sh:minCount 1 ;",
        f"        sh:datatype xsd:string ;",
        f'        sh:pattern "^[A-Z][A-Za-z0-9]*$" ;',
        f'        sh:message "Entity name must be PascalCase (sh:pattern violation)" ;',
        f"    ] ;",
        f"    sh:property [",
        f"        sh:path cdm:description ;",
        f"        sh:minCount 1 ;",
        f"        sh:minLength 5 ;",
        f'        sh:message "Entity must have a description of at least 5 characters" ;',
        f"    ] .",
        f"",
    ]

    # Dimension shapes
    for d in domain.get("dimension_concepts", []):
        name = d.get("name","").strip()
        if not name: continue
        attrs = d.get("attributes", [])
        lines += [
            f"cdm:{name}Shape a sh:NodeShape ;",
            f"    sh:targetClass cdm:{name} ;",
            f"    sh:closed false ;",
        ]
        for attr in attrs[:3]:
            attr_clean = re.sub(r'[^A-Za-z0-9]', '', attr)
            lines += [
                f"    sh:property [",
                f"        sh:path cdm:{name}_{attr_clean} ;",
                f"        sh:datatype xsd:string ;",
                f'        sh:name "{attr}" ;',
                f"    ] ;",
            ]
        lines += [f"    sh:message \"Shape validation for {name}\" .", ""]

    # Fact shapes
    for f in domain.get("fact_concepts", []):
        name = f.get("name","").strip()
        if not name: continue
        metrics = f.get("metrics", [])
        lines += [
            f"cdm:{name}Shape a sh:NodeShape ;",
            f"    sh:targetClass cdm:{name} ;",
            f"    sh:property [",
            f"        sh:path cdm:effectiveDate ;",
            f"        sh:datatype xsd:date ;",
            f'        sh:name "Effective Date" ;',
            f"        sh:minCount 1 ;",
            f"    ] ;",
        ]
        for metric in metrics[:3]:
            metric_clean = re.sub(r'[^A-Za-z0-9]', '', metric)
            lines += [
                f"    sh:property [",
                f"        sh:path cdm:{name}_{metric_clean} ;",
                f"        sh:datatype xsd:decimal ;",
                f'        sh:name "{metric}" ;',
                f"    ] ;",
            ]
        lines += [f"    sh:message \"Shape validation for {name}\" .", ""]

    # Forbidden pattern shapes
    forbidden = domain.get("forbidden_patterns", [])
    if forbidden:
        lines += [
            f"# ── Forbidden entity name constraints ───────────────────────────────────────",
            f"cdm:ForbiddenNamesShape a sh:NodeShape ;",
            f"    sh:targetClass cdm:DimensionEntity, cdm:FactEntity, cdm:ReferenceEntity ;",
        ]
        for fp in forbidden[:10]:
            fp_clean = fp.replace('"',"'")
            lines += [
                f"    sh:not [",
                f"        sh:property [",
                f"            sh:path cdm:name ;",
                f'            sh:hasValue "{fp_clean}" ;',
                f"        ] ;",
                f"    ] ;",
            ]
        lines += [f"    sh:message \"Entity matches a forbidden pattern from the BRD\" .", ""]

    return "\n".join(lines)


# ── SKILL.md updater ──────────────────────────────────────────────────────────

def _update_skill_md(domain: dict) -> str:
    """Generate a BRD-specific SKILL.md section to append to the base skill."""

    domain_name = domain.get("domain_name", "BusinessDomain")
    dim_names   = [d.get("name","") for d in domain.get("dimension_concepts", [])]
    fact_names  = [f.get("name","") for f in domain.get("fact_concepts", [])]
    ref_names   = [r.get("name","") for r in domain.get("reference_concepts", [])]
    forbidden   = domain.get("forbidden_patterns", [])
    metrics     = domain.get("key_metrics", [])
    filters     = domain.get("filters_and_prompts", [])

    lines = [
        f"",
        f"---",
        f"",
        f"## BRD-SPECIFIC RULES — {domain_name}",
        f"*Auto-generated by Step 1b from the uploaded BRD*",
        f"",
        f"### Expected Dimension entities",
    ]
    for n in dim_names:
        lines.append(f"- `{n}`")

    lines += ["", "### Expected Fact entities"]
    for n in fact_names:
        lines.append(f"- `{n}`")

    lines += ["", "### Expected Reference entities"]
    for n in ref_names:
        lines.append(f"- `{n}`")

    if forbidden:
        lines += ["", "### BRD-specific forbidden patterns (MUST NOT become entities)"]
        for fp in forbidden:
            lines.append(f"- `{fp}`")

    if metrics:
        lines += ["", "### Key metrics (attributes of Fact entities — NOT standalone entities)"]
        for m in metrics:
            lines.append(f"- `{m}`")

    if filters:
        lines += ["", "### Filter/Prompt → Dimension mappings (Rule R6 — BRD specific)"]
        for f in filters:
            lines.append(
                f"- `{f.get('filter_name','')}` → `{f.get('implied_dimension','')}`"
            )

    return "\n".join(lines)


# ── Main step function ────────────────────────────────────────────────────────

def build_ontology_from_brd(
    brd_text: str,
    ollama_url: str,
    model: str,
    temperature: float = 0.1,
    on_log=None,
) -> dict:
    """
    Main entry point for Step 1b.
    Returns a domain dict with extracted concepts and paths to generated files.
    """
    def log(msg):
        if on_log: on_log(msg)

    log("Extracting domain vocabulary from BRD…")

    chunk = brd_text[:5000] if len(brd_text) > 5000 else brd_text

    try:
        raw = chat(
            base_url=ollama_url,
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_DOMAIN},
                {"role": "user",   "content": USER_DOMAIN.format(brd_text=chunk)},
            ],
            temperature=temperature,
            format="json",
        )
        domain = extract_json(raw)
        if not isinstance(domain, dict):
            domain = {}
    except Exception as e:
        log(f"Domain extraction failed: {e} — using empty domain")
        domain = {}

    domain_name = domain.get("domain_name", "BusinessDomain")
    log(f"Domain identified: {domain_name}")

    # ── Generate OWL ontology ─────────────────────────────────────────────────
    log("Generating OWL ontology (Turtle format)…")
    owl_content = _generate_owl(domain)
    owl_path    = os.path.join(GENERATED_DIR, f"{domain_name}_ontology.ttl")
    with open(owl_path, "w", encoding="utf-8") as f:
        f.write(owl_content)
    log(f"OWL written → ontology/generated/{domain_name}_ontology.ttl")

    # ── Generate SHACL shapes ─────────────────────────────────────────────────
    log("Generating SHACL shapes…")
    shacl_content = _generate_shacl(domain)
    shacl_path    = os.path.join(GENERATED_DIR, f"{domain_name}_shapes.ttl")
    with open(shacl_path, "w", encoding="utf-8") as f:
        f.write(shacl_content)
    log(f"SHACL written → ontology/generated/{domain_name}_shapes.ttl")

    # ── Save domain JSON ──────────────────────────────────────────────────────
    domain_json_path = os.path.join(GENERATED_DIR, f"{domain_name}_domain.json")
    with open(domain_json_path, "w", encoding="utf-8") as f:
        json.dump(domain, f, indent=2)

    # ── Update SKILL.md ───────────────────────────────────────────────────────
    log("Updating SKILL.md with BRD-specific rules…")
    try:
        # Read base SKILL.md
        base_skill = ""
        if os.path.exists(BASE_SKILL_PATH):
            with open(BASE_SKILL_PATH, "r", encoding="utf-8") as f:
                base_skill = f.read()
        elif os.path.exists(SKILL_PATH):
            with open(SKILL_PATH, "r", encoding="utf-8") as f:
                content = f.read()
            # Remove any previously generated BRD-specific section
            marker = "\n---\n\n## BRD-SPECIFIC RULES"
            idx = content.find(marker)
            base_skill = content[:idx] if idx != -1 else content
            # Save base for next run
            with open(BASE_SKILL_PATH, "w", encoding="utf-8") as f:
                f.write(base_skill)

        # Append BRD-specific section
        brd_section  = _update_skill_md(domain)
        updated_skill = base_skill + brd_section
        with open(SKILL_PATH, "w", encoding="utf-8") as f:
            f.write(updated_skill)
        log("SKILL.md updated with BRD-specific guardrails")
    except Exception as e:
        log(f"SKILL.md update warning: {e}")

    domain["_owl_path"]   = owl_path
    domain["_shacl_path"] = shacl_path
    domain["_domain_name"]= domain_name

    dim_count  = len(domain.get("dimension_concepts", []))
    fact_count = len(domain.get("fact_concepts", []))
    ref_count  = len(domain.get("reference_concepts", []))
    log(f"Ontology built: {dim_count} dimensions, {fact_count} facts, {ref_count} references")

    return domain
