"""
Generate standalone SVG architecture diagrams for DataModelerAgent.

Fully local, no external services or system dependencies — emits crisp vector
SVGs that embed directly into slides (PowerPoint: Insert > Pictures > .svg).

Run:  python diagrams/generate_diagrams.py
Output: diagrams/architecture_layers.svg, diagrams/architecture_flow.svg
"""

import html
import math
import os

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

FONT = "Segoe UI, Helvetica, Arial, sans-serif"


def esc(s):
    return html.escape(str(s))


def lighten(hex_color, amount):
    """Mix a hex color toward white by `amount` (0..1)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r = int(r + (255 - r) * amount)
    g = int(g + (255 - g) * amount)
    b = int(b + (255 - b) * amount)
    return f"#{r:02x}{g:02x}{b:02x}"


def multiline(text, cx, cy, line_h, cls):
    """Render \n-separated text as vertically-centered <tspan>s."""
    lines = text.split("\n")
    total = (len(lines) - 1) * line_h
    start = cy - total / 2
    spans = "".join(
        f'<tspan x="{cx}" y="{start + i * line_h:.1f}">{esc(ln)}</tspan>'
        for i, ln in enumerate(lines)
    )
    return f'<text class="{cls}" text-anchor="middle">{spans}</text>'


# ──────────────────────────────────────────────────────────────────────────────
# Diagram 1 — Layered architecture
# ──────────────────────────────────────────────────────────────────────────────

def layered_diagram():
    W = 1240
    LEFT, RIGHT = 50, W - 50
    INNER_W = RIGHT - LEFT
    GAP = 16
    ROW_H = 48
    ROW_GAP = 12
    TITLE_PAD = 34
    BOT_PAD = 16
    BOX_GAP = 18

    bands = [
        ("UI Layer — Streamlit  (app.py)", "#3B6FD4", 1, False,
         ["Sidebar\n(config)", "Upload\n(file + mode)",
          "Pipeline UI\n(progress)", "Output · Graph · LDM\n(results)"]),
        ("Orchestration", "#6A5ACD", 1, False,
         ["CDM Pipeline — pipeline_agent.py\n(8 steps + hash cache)",
          "LDM Pipeline — ldm_pipeline.py\n(3 steps + repair loop)"]),
        ("Pipeline Steps", "#1F9E8C", 2, False,
         ["1 · Parse", "1b · Ontology", "2 · GraphRAG", "2 · Entities",
          "3 · Relationships", "4 · Ontology Enrich", "4b · OWL/SHACL",
          "CDM Assembly", "LDM Promote", "LDM Validate", "LDM DDL"]),
        ("Support & Utilities", "#C9881F", 1, False,
         ["ollama_client", "result_store", "ldm_conventions",
          "ldm_seeder", "skill_loader"]),
        ("Knowledge & Rules", "#B5476A", 1, False,
         ["OWL R1–R6 + SHACL\n(ontology/rules.py)",
          "schema.org seed\n(ontology/seeder.py)",
          "SKILL.md\n(entity guardrails)",
          "LDM_NAMING_\nCONVENTIONS.md"]),
        ("External Services", "#566573", 1, True,
         ["Ollama\n(local LLM)", "Neo4j Aura\n(knowledge graph)",
          "ChromaDB\n(vector store)"]),
    ]

    # Pre-compute band heights / y positions
    y = 78
    placed = []
    for title, color, rows, is_db, items in bands:
        h = TITLE_PAD + rows * ROW_H + (rows - 1) * ROW_GAP + BOT_PAD
        placed.append((y, h, title, color, rows, is_db, items))
        y += h + GAP
    total_h = y - GAP + 40

    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{total_h}" '
        f'viewBox="0 0 {W} {total_h}" font-family="{FONT}">'
    )
    parts.append(f'''<style>
      .title {{ font-size: 26px; font-weight: 700; fill: #1b2733; }}
      .sub   {{ font-size: 13px; fill: #5b6b7b; }}
      .band  {{ font-size: 15px; font-weight: 700; }}
      .box   {{ font-size: 13.5px; fill: #1b2733; }}
      .boxb  {{ font-size: 14px; font-weight: 600; fill: #ffffff; }}
    </style>''')
    parts.append(f'<rect x="0" y="0" width="{W}" height="{total_h}" fill="#ffffff"/>')
    parts.append('<text x="50" y="42" class="title">DataModelerAgent — Layered Architecture</text>')
    parts.append('<text x="50" y="64" class="sub">BRD (.docx) &#8594; Conceptual Data Model &#8594; Logical Data Model + SQL DDL</text>')

    # Downward flow arrow on the right gutter
    arrow_x = RIGHT + 18
    if arrow_x < W - 10:
        pass  # keep within canvas; skip if tight

    for idx, (by, bh, title, color, rows, is_db, items) in enumerate(placed):
        tint = lighten(color, 0.86)
        parts.append(
            f'<rect x="{LEFT}" y="{by}" width="{INNER_W}" height="{bh}" rx="12" '
            f'fill="{tint}" stroke="{color}" stroke-width="1.5"/>'
        )
        # Band title chip
        parts.append(
            f'<rect x="{LEFT}" y="{by}" width="232" height="26" rx="12" fill="{color}"/>'
        )
        parts.append(
            f'<text class="band" x="{LEFT + 14}" y="{by + 18}" fill="#ffffff">{esc(title)}</text>'
        )

        # Boxes
        per_row = math.ceil(len(items) / rows)
        box_w = (INNER_W - 28 - (per_row - 1) * BOX_GAP) / per_row
        for i, label in enumerate(items):
            r = i // per_row
            c = i % per_row
            # last row may have fewer items -> center them
            items_in_row = min(per_row, len(items) - r * per_row)
            row_w = items_in_row * box_w + (items_in_row - 1) * BOX_GAP
            row_x0 = LEFT + (INNER_W - row_w) / 2
            bx = row_x0 + c * (box_w + BOX_GAP)
            byy = by + TITLE_PAD + r * (ROW_H + ROW_GAP)
            cx = bx + box_w / 2
            cy = byy + ROW_H / 2
            if is_db:
                # cylinder
                rx = box_w / 2
                ry = 8
                top = byy + ry
                bot = byy + ROW_H - ry
                d = (f'M{bx},{top} A{rx},{ry} 0 0 1 {bx + box_w},{top} '
                     f'L{bx + box_w},{bot} A{rx},{ry} 0 0 1 {bx},{bot} Z')
                parts.append(f'<path d="{d}" fill="{color}"/>')
                parts.append(
                    f'<ellipse cx="{cx}" cy="{top}" rx="{rx}" ry="{ry}" '
                    f'fill="{lighten(color, 0.2)}"/>'
                )
                parts.append(multiline(label, cx, cy + 4, 16, "boxb"))
            else:
                parts.append(
                    f'<rect x="{bx:.1f}" y="{byy}" width="{box_w:.1f}" height="{ROW_H}" '
                    f'rx="9" fill="#ffffff" stroke="{color}" stroke-width="1.4"/>'
                )
                parts.append(multiline(label, cx, cy + 1, 15, "box"))

        # connector arrow to next band
        if idx < len(placed) - 1:
            ax = W / 2
            y1 = by + bh
            y2 = y1 + GAP
            parts.append(
                f'<line x1="{ax}" y1="{y1}" x2="{ax}" y2="{y2 - 2}" '
                f'stroke="#90a0b0" stroke-width="2" marker-end="url(#ah)"/>'
            )

    parts.append('''<defs>
      <marker id="ah" markerWidth="9" markerHeight="9" refX="6" refY="4.5"
              orient="auto"><path d="M0,0 L9,4.5 L0,9 Z" fill="#90a0b0"/></marker>
    </defs>''')
    parts.append('</svg>')
    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# Diagram 2 — End-to-end data flow
# ──────────────────────────────────────────────────────────────────────────────

def flow_diagram():
    W = 1080
    CX = 340          # main spine center
    BOX_W = 360
    BOX_H = 46
    VGAP = 26
    top = 90

    # (label, accent, side-tag)
    steps = [
        ("BRD document  (.docx)", "#334155", None),
        ("Step 1 · Parse  (LlamaParse → docx)", "#1F9E8C", None),
        ("Step 1b · Ontology Build  (1 LLM call)", "#1F9E8C", "Ollama"),
        ("Step 2 · GraphRAG  (chunk → graph → retrieve)", "#1F9E8C", "Neo4j Aura"),
        ("Step 3 · Entity Extraction  (2-pass)", "#1F9E8C", "Ollama"),
        ("Step 4 · Relationship Detection  (2-pass)", "#1F9E8C", "Ollama"),
        ("Step 5 · Ontology Enrichment", "#1F9E8C", "ChromaDB"),
        ("Step 6 · OWL / SHACL Rules  (R1–R6)", "#1F9E8C", None),
        ("Step 7 · CDM Assembly  (no LLM)", "#3B6FD4", None),
    ]
    ldm_steps = [
        ("Step A · Seed Oracle reference", "#B5476A", "ChromaDB"),
        ("Step B · CDM → LDM Promotion  (2 LLM calls)", "#B5476A", "Ollama"),
        ("Step V · Validation Agent  (≤3 repairs)", "#B5476A", "Ollama"),
        ("Step F · DDL Generation  (no LLM)", "#B5476A", None),
        ("Outputs: CDM + LDM diagrams · SQL DDL · JSON-LD", "#6A5ACD", None),
    ]

    parts = []
    body = []

    def box(cx, y, w, h, label, color, fill="#ffffff", text_fill="#1b2733",
            font=14, weight=600):
        body.append(
            f'<rect x="{cx - w/2:.1f}" y="{y}" width="{w}" height="{h}" rx="9" '
            f'fill="{fill}" stroke="{color}" stroke-width="1.6"/>'
        )
        body.append(
            f'<text x="{cx}" y="{y + h/2 + 5:.1f}" text-anchor="middle" '
            f'font-size="{font}px" font-weight="{weight}" fill="{text_fill}">{esc(label)}</text>'
        )

    def arrow(y1, y2, cx=CX, label=None):
        body.append(
            f'<line x1="{cx}" y1="{y1}" x2="{cx}" y2="{y2 - 2}" stroke="#90a0b0" '
            f'stroke-width="2" marker-end="url(#ah2)"/>'
        )
        if label:
            body.append(
                f'<text x="{cx + 10}" y="{(y1 + y2)/2 + 4:.1f}" font-size="12px" '
                f'fill="#5b6b7b" font-style="italic">{esc(label)}</text>'
            )

    def tag(cx_box, y, name):
        tw = 8 + len(name) * 7.2
        tx = cx_box + BOX_W / 2 + 26
        body.append(
            f'<rect x="{tx:.1f}" y="{y + 11:.1f}" width="{tw:.1f}" height="24" rx="12" '
            f'fill="#eef2f7" stroke="#b9c4d0" stroke-width="1"/>'
        )
        body.append(
            f'<text x="{tx + tw/2:.1f}" y="{y + 27:.1f}" text-anchor="middle" '
            f'font-size="12px" fill="#566573">{esc(name)}</text>'
        )
        body.append(
            f'<line x1="{cx_box + BOX_W/2}" y1="{y + BOX_H/2:.1f}" x2="{tx:.1f}" '
            f'y2="{y + BOX_H/2:.1f}" stroke="#b9c4d0" stroke-width="1.2" '
            f'stroke-dasharray="3,3"/>'
        )

    y = top
    first = True
    for label, color, side in steps:
        if not first:
            arrow(y - VGAP, y)
        box(CX, y, BOX_W, BOX_H, label, color,
            fill=lighten(color, 0.9) if color == "#3B6FD4" else "#ffffff")
        if side:
            tag(CX, y, side)
        first = False
        y += BOX_H + VGAP

    # decision diamond (mode)
    dy = y
    dsz = 58
    body.append(
        f'<path d="M{CX},{dy} L{CX + dsz},{dy + dsz/2} L{CX},{dy + dsz} '
        f'L{CX - dsz},{dy + dsz/2} Z" fill="#fff7e6" stroke="#C9881F" stroke-width="1.6"/>'
    )
    body.append(
        f'<text x="{CX}" y="{dy + dsz/2 + 4:.1f}" text-anchor="middle" '
        f'font-size="13px" font-weight="600" fill="#8a5b10">mode?</text>'
    )
    arrow(y - VGAP, dy)

    # CDM-only branch -> right
    bxr = CX + 250
    body.append(
        f'<line x1="{CX + dsz}" y1="{dy + dsz/2}" x2="{bxr - 120}" y2="{dy + dsz/2}" '
        f'stroke="#90a0b0" stroke-width="2" marker-end="url(#ah2)"/>'
    )
    body.append(
        f'<text x="{CX + dsz + 8}" y="{dy + dsz/2 - 6:.1f}" font-size="12px" '
        f'fill="#5b6b7b" font-style="italic">CDM only</text>'
    )
    box(bxr, dy + dsz/2 - BOX_H/2, 230, BOX_H, "Render CDM", "#3B6FD4",
        fill=lighten("#3B6FD4", 0.9))

    y = dy + dsz + VGAP
    arrow(dy + dsz, y, label="CDM + LDM")

    first = True
    for label, color, side in ldm_steps:
        if not first:
            arrow(y - VGAP, y)
        box(CX, y, BOX_W, BOX_H, label, color,
            fill=lighten(color, 0.9) if color == "#6A5ACD" else "#ffffff")
        if side:
            tag(CX, y, side)
        first = False
        y += BOX_H + VGAP

    total_h = y + 20

    # cache note box (left side, near CDM assembly)
    body.append(
        f'<rect x="40" y="{top + 7*(BOX_H+VGAP):.1f}" width="170" height="62" rx="9" '
        f'fill="#f4f0fb" stroke="#6A5ACD" stroke-width="1.3" stroke-dasharray="4,3"/>'
    )
    body.append(
        f'<text x="125" y="{top + 7*(BOX_H+VGAP) + 26:.1f}" text-anchor="middle" '
        f'font-size="12px" font-weight="600" fill="#4b3b8f">hash cache</text>'
    )
    body.append(
        f'<text x="125" y="{top + 7*(BOX_H+VGAP) + 44:.1f}" text-anchor="middle" '
        f'font-size="11px" fill="#5b6b7b">ontology/generated/</text>'
    )

    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{total_h}" '
        f'viewBox="0 0 {W} {total_h}" font-family="{FONT}">'
    )
    parts.append(f'<rect x="0" y="0" width="{W}" height="{total_h}" fill="#ffffff"/>')
    parts.append(f'<text x="40" y="42" font-size="26px" font-weight="700" fill="#1b2733">DataModelerAgent — End-to-End Data Flow</text>')
    parts.append('<text x="40" y="64" font-size="13px" fill="#5b6b7b">Side tags mark the external service each step calls.</text>')
    parts.append("\n".join(body))
    parts.append('''<defs>
      <marker id="ah2" markerWidth="9" markerHeight="9" refX="6" refY="4.5"
              orient="auto"><path d="M0,0 L9,4.5 L0,9 Z" fill="#90a0b0"/></marker>
    </defs>''')
    parts.append('</svg>')
    return "\n".join(parts)


def main():
    for name, svg in (
        ("architecture_layers.svg", layered_diagram()),
        ("architecture_flow.svg", flow_diagram()),
    ):
        path = os.path.join(OUT_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"wrote {path}  ({len(svg):,} bytes)")


if __name__ == "__main__":
    main()
