"""
Graph view — renders entities and relationships as an interactive
network graph using a pure SVG/HTML implementation with no external CDN.
Works fully offline. Uses a simple force-directed layout in JavaScript.
"""

import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import streamlit.components.v1 as components

# Colour scheme per entity type
TYPE_COLORS = {
    "dimension": "#1F6FEB",
    "fact":      "#DA3633",
    "reference": "#484F58",
    "bridge":    "#8957E5",
    "report":    "#F97316",
}
DEFAULT_COLOR = "#238636"

TYPE_SHAPES = {
    "dimension": "ellipse",
    "fact":      "rect",
    "reference": "diamond",
    "bridge":    "hexagon",
    "report":    "star",
}


def _build_graph_data(result: dict, show_inferred: bool, show_reports: bool):
    entities = result.get("entities", [])
    relationships = result.get("relationships", [])

    filtered = [
        e for e in entities
        if (show_inferred or not e.get("inferred"))
        and (show_reports or e.get("type") != "report")
    ]

    name_to_id = {e["name"]: i for i, e in enumerate(filtered)}

    nodes = []
    for i, e in enumerate(filtered):
        etype = e.get("type", "dimension")
        nodes.append({
            "id":    i,
            "label": e.get("name", ""),
            "type":  etype,
            "color": TYPE_COLORS.get(etype, DEFAULT_COLOR),
            "shape": TYPE_SHAPES.get(etype, "ellipse"),
            "desc":  e.get("description", ""),
            "inferred": e.get("inferred", False),
        })

    edges = []
    seen = set()
    for r in relationships:
        from_e = r.get("from_entity", "")
        to_e   = r.get("to_entity", "")
        if from_e not in name_to_id or to_e not in name_to_id:
            continue
        key = (from_e, to_e, r.get("label", ""))
        if key in seen:
            continue
        seen.add(key)
        edges.append({
            "from":    name_to_id[from_e],
            "to":      name_to_id[to_e],
            "label":   r.get("label", ""),
            "card":    r.get("cardinality", ""),
            "dashed":  r.get("inferred", False),
        })

    return nodes, edges


def _build_html(nodes: list, edges: list, height: int = 560) -> str:
    nodes_json = json.dumps(nodes)
    edges_json = json.dumps(edges)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:#0D1117; font-family: system-ui, sans-serif; overflow:hidden; }}
#canvas {{ display:block; }}
#legend {{
    position:fixed; top:10px; right:10px;
    background:rgba(22,27,34,0.92);
    border:1px solid #30363D;
    border-radius:8px; padding:10px 14px;
    font-size:12px; color:#C9D1D9;
}}
.li {{ display:flex; align-items:center; gap:8px; margin-bottom:5px; }}
.dot {{ width:12px; height:12px; border-radius:3px; flex-shrink:0; }}
#tooltip {{
    position:fixed; display:none;
    background:rgba(22,27,34,0.95);
    border:1px solid #30363D;
    border-radius:6px; padding:8px 12px;
    font-size:11px; color:#C9D1D9;
    max-width:240px; pointer-events:none;
    line-height:1.5;
}}
#controls {{
    position:fixed; bottom:10px; left:10px;
    display:flex; gap:6px;
}}
button {{
    background:#21262D; color:#C9D1D9;
    border:1px solid #30363D; border-radius:6px;
    padding:5px 10px; font-size:11px; cursor:pointer;
}}
button:hover {{ background:#30363D; }}
</style>
</head>
<body>
<canvas id="canvas" width="1200" height="{height}"></canvas>
<div id="legend">
  <div class="li"><div class="dot" style="background:#1F6FEB"></div>Dimension</div>
  <div class="li"><div class="dot" style="background:#DA3633"></div>Fact</div>
  <div class="li"><div class="dot" style="background:#484F58"></div>Reference</div>
  <div class="li"><div class="dot" style="background:#8957E5"></div>Bridge</div>
  <div class="li"><div class="dot" style="background:#F97316"></div>Report</div>
  <div class="li" style="margin-top:6px;border-top:1px solid #30363D;padding-top:6px">
    <span style="color:#8B949E;font-size:10px">Dashed = inferred</span>
  </div>
</div>
<div id="tooltip"></div>
<div id="controls">
  <button onclick="resetLayout()">⊞ Reset layout</button>
  <button onclick="zoomFit()">⟳ Fit all</button>
</div>
<script>
const W = 1200, H = {height};
const canvas = document.getElementById('canvas');
const ctx    = canvas.getContext('2d');
const tooltip = document.getElementById('tooltip');

const nodesData = {nodes_json};
const edgesData = {edges_json};

// ── Layout state ──────────────────────────────────────────────────────────────
let nodes = nodesData.map((n, i) => ({{
  ...n,
  x: W/2 + (Math.random()-0.5)*400,
  y: H/2 + (Math.random()-0.5)*300,
  vx: 0, vy: 0,
  r: n.type === 'fact' ? 36 : 28,
}}));

let pan = {{x:0, y:0}};
let scale = 1;
let dragging = null, dragOffX = 0, dragOffY = 0;
let panning = false, panStart = {{x:0, y:0}}, panOrigin = {{x:0, y:0}};
let hoveredNode = null;
let simRunning = true;
let simTick = 0;

// ── Force simulation ──────────────────────────────────────────────────────────
function simulate() {{
  if (!simRunning) return;
  simTick++;

  const k = Math.sqrt((W * H) / Math.max(nodes.length, 1));
  const REPEL  = k * k * 1.8;
  const SPRING = 0.04;
  const DAMP   = 0.82;
  const CENTER = 0.015;

  // Repulsion
  for (let i = 0; i < nodes.length; i++) {{
    nodes[i].vx *= DAMP;
    nodes[i].vy *= DAMP;
    // Center gravity
    nodes[i].vx += (W/2 - nodes[i].x) * CENTER;
    nodes[i].vy += (H/2 - nodes[i].y) * CENTER;
    for (let j = i+1; j < nodes.length; j++) {{
      const dx = nodes[i].x - nodes[j].x;
      const dy = nodes[i].y - nodes[j].y;
      const dist = Math.sqrt(dx*dx + dy*dy) || 1;
      const force = REPEL / dist;
      nodes[i].vx += (dx/dist) * force / nodes.length;
      nodes[i].vy += (dy/dist) * force / nodes.length;
      nodes[j].vx -= (dx/dist) * force / nodes.length;
      nodes[j].vy -= (dy/dist) * force / nodes.length;
    }}
  }}

  // Spring attraction (edges)
  const ideal = k * 2.2;
  for (const e of edgesData) {{
    const a = nodes[e.from], b = nodes[e.to];
    if (!a || !b) continue;
    const dx = b.x - a.x, dy = b.y - a.y;
    const dist = Math.sqrt(dx*dx + dy*dy) || 1;
    const force = (dist - ideal) * SPRING;
    a.vx += (dx/dist) * force;
    a.vy += (dy/dist) * force;
    b.vx -= (dx/dist) * force;
    b.vy -= (dy/dist) * force;
  }}

  // Integrate
  for (const n of nodes) {{
    if (dragging && n.id === dragging.id) continue;
    n.x += Math.max(-20, Math.min(20, n.vx));
    n.y += Math.max(-20, Math.min(20, n.vy));
    n.x = Math.max(n.r, Math.min(W - n.r, n.x));
    n.y = Math.max(n.r, Math.min(H - n.r, n.y));
  }}

  if (simTick > 300) simRunning = false;
}}

// ── Draw ──────────────────────────────────────────────────────────────────────
function drawArrow(x1, y1, x2, y2, dashed, label, card) {{
  ctx.save();
  ctx.strokeStyle = hoveredNode !== null && (
    edgesData.find(e => (e.from === hoveredNode || e.to === hoveredNode) &&
      nodes[e.from] && nodes[e.to] &&
      ((nodes[e.from].x === x1 && nodes[e.from].y === y1) ||
       (nodes[e.to].x === x2 && nodes[e.to].y === y2)))
  ) ? '#58A6FF' : '#484F58';
  ctx.lineWidth = 1.5;
  if (dashed) ctx.setLineDash([5, 4]);
  else ctx.setLineDash([]);

  const angle = Math.atan2(y2-y1, x2-x1);
  const arrowLen = 10;
  const tx = x2 - Math.cos(angle)*14;
  const ty = y2 - Math.sin(angle)*14;

  ctx.beginPath();
  ctx.moveTo(x1 + Math.cos(angle)*16, y1 + Math.sin(angle)*16);
  ctx.lineTo(tx, ty);
  ctx.stroke();

  // Arrow head
  ctx.setLineDash([]);
  ctx.fillStyle = ctx.strokeStyle;
  ctx.beginPath();
  ctx.moveTo(tx, ty);
  ctx.lineTo(tx - arrowLen*Math.cos(angle-0.4), ty - arrowLen*Math.sin(angle-0.4));
  ctx.lineTo(tx - arrowLen*Math.cos(angle+0.4), ty - arrowLen*Math.sin(angle+0.4));
  ctx.closePath();
  ctx.fill();

  // Edge label
  if (label) {{
    const mx = (x1+x2)/2, my = (y1+y2)/2;
    ctx.font = '10px system-ui';
    ctx.fillStyle = '#8B949E';
    ctx.textAlign = 'center';
    ctx.fillText(label + (card ? ' ['+card+']' : ''), mx, my - 6);
  }}
  ctx.restore();
}}

function drawNode(n) {{
  const isHovered = hoveredNode === n.id;
  ctx.save();
  ctx.shadowColor = isHovered ? '#fff' : 'rgba(0,0,0,0.5)';
  ctx.shadowBlur  = isHovered ? 12 : 6;

  const r = n.r;
  ctx.fillStyle   = n.color;
  ctx.strokeStyle = isHovered ? '#fff' : 'rgba(255,255,255,0.15)';
  ctx.lineWidth   = isHovered ? 2.5 : 1.5;

  if (n.type === 'fact') {{
    // Rectangle for facts
    ctx.beginPath();
    ctx.roundRect(n.x-r, n.y-r*0.65, r*2, r*1.3, 8);
    ctx.fill(); ctx.stroke();
  }} else if (n.type === 'reference') {{
    // Diamond
    ctx.beginPath();
    ctx.moveTo(n.x, n.y-r);
    ctx.lineTo(n.x+r, n.y);
    ctx.lineTo(n.x, n.y+r);
    ctx.lineTo(n.x-r, n.y);
    ctx.closePath();
    ctx.fill(); ctx.stroke();
  }} else {{
    // Ellipse for dimension/bridge/report
    ctx.beginPath();
    ctx.ellipse(n.x, n.y, r, r*0.65, 0, 0, Math.PI*2);
    ctx.fill(); ctx.stroke();
  }}

  // Label
  ctx.shadowBlur = 0;
  ctx.fillStyle  = '#fff';
  ctx.font       = `${{isHovered ? 'bold ' : ''}}11px system-ui`;
  ctx.textAlign  = 'center';
  ctx.textBaseline = 'middle';

  // Wrap long labels
  const words = n.label.replace(/([A-Z])/g, ' $1').trim().split(' ');
  if (words.length <= 2) {{
    ctx.fillText(n.label, n.x, n.y);
  }} else {{
    const mid = Math.ceil(words.length/2);
    ctx.fillText(words.slice(0,mid).join(''), n.x, n.y-7);
    ctx.fillText(words.slice(mid).join(''), n.x, n.y+7);
  }}

  // Inferred badge
  if (n.inferred) {{
    ctx.font = '9px system-ui';
    ctx.fillStyle = 'rgba(255,255,255,0.5)';
    ctx.fillText('inferred', n.x, n.y + r*0.65 + 10);
  }}

  ctx.restore();
}}

function draw() {{
  ctx.clearRect(0, 0, W, H);
  ctx.save();
  ctx.translate(pan.x, pan.y);
  ctx.scale(scale, scale);

  // Edges first
  for (const e of edgesData) {{
    const a = nodes[e.from], b = nodes[e.to];
    if (!a || !b) continue;
    drawArrow(a.x, a.y, b.x, b.y, e.dashed, e.label, e.card);
  }}

  // Nodes on top
  for (const n of nodes) drawNode(n);

  ctx.restore();
}}

function loop() {{
  simulate();
  draw();
  requestAnimationFrame(loop);
}}

// ── Interaction ───────────────────────────────────────────────────────────────
function screenToWorld(sx, sy) {{
  return {{ x: (sx - pan.x) / scale, y: (sy - pan.y) / scale }};
}}

function nodeAt(wx, wy) {{
  for (let i = nodes.length-1; i >= 0; i--) {{
    const n = nodes[i];
    const dx = wx - n.x, dy = wy - n.y;
    if (Math.sqrt(dx*dx + dy*dy) < n.r + 6) return n;
  }}
  return null;
}}

canvas.addEventListener('mousedown', e => {{
  const {{x, y}} = screenToWorld(e.offsetX, e.offsetY);
  const n = nodeAt(x, y);
  if (n) {{
    dragging = n; dragOffX = n.x - x; dragOffY = n.y - y;
    simRunning = true; simTick = 0;
  }} else {{
    panning = true;
    panStart = {{x: e.offsetX, y: e.offsetY}};
    panOrigin = {{...pan}};
  }}
}});

canvas.addEventListener('mousemove', e => {{
  if (dragging) {{
    const {{x, y}} = screenToWorld(e.offsetX, e.offsetY);
    dragging.x = x + dragOffX;
    dragging.y = y + dragOffY;
    dragging.vx = 0; dragging.vy = 0;
  }} else if (panning) {{
    pan.x = panOrigin.x + (e.offsetX - panStart.x);
    pan.y = panOrigin.y + (e.offsetY - panStart.y);
  }} else {{
    const {{x, y}} = screenToWorld(e.offsetX, e.offsetY);
    const n = nodeAt(x, y);
    hoveredNode = n ? n.id : null;
    canvas.style.cursor = n ? 'pointer' : 'default';
    if (n) {{
      tooltip.style.display = 'block';
      tooltip.style.left = (e.clientX + 14) + 'px';
      tooltip.style.top  = (e.clientY - 10) + 'px';
      tooltip.innerHTML = `<b>${{n.label}}</b><br><span style="color:#8B949E">${{n.type}}</span><br>${{n.desc||''}}`;
    }} else {{
      tooltip.style.display = 'none';
    }}
  }}
}});

canvas.addEventListener('mouseup', () => {{ dragging = null; panning = false; }});
canvas.addEventListener('mouseleave', () => {{
  dragging = null; panning = false;
  tooltip.style.display = 'none'; hoveredNode = null;
}});

canvas.addEventListener('wheel', e => {{
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.1 : 0.9;
  const wx = (e.offsetX - pan.x) / scale;
  const wy = (e.offsetY - pan.y) / scale;
  scale *= factor;
  scale = Math.max(0.2, Math.min(4, scale));
  pan.x = e.offsetX - wx * scale;
  pan.y = e.offsetY - wy * scale;
}}, {{passive: false}});

function resetLayout() {{
  nodes.forEach((n, i) => {{
    n.x = W/2 + (Math.random()-0.5)*400;
    n.y = H/2 + (Math.random()-0.5)*300;
    n.vx = 0; n.vy = 0;
  }});
  pan = {{x:0, y:0}}; scale = 1;
  simRunning = true; simTick = 0;
}}

function zoomFit() {{
  if (!nodes.length) return;
  let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
  nodes.forEach(n => {{
    minX=Math.min(minX,n.x-n.r); maxX=Math.max(maxX,n.x+n.r);
    minY=Math.min(minY,n.y-n.r); maxY=Math.max(maxY,n.y+n.r);
  }});
  const pad = 40;
  const sx = (W-pad*2)/(maxX-minX||1);
  const sy = (H-pad*2)/(maxY-minY||1);
  scale = Math.min(sx, sy, 2);
  pan.x = pad - minX*scale;
  pan.y = pad - minY*scale;
}}

loop();
</script>
</body>
</html>"""


def render_graph(result: dict, height: int = 580):
    entities      = result.get("entities", [])
    relationships = result.get("relationships", [])

    if not entities:
        st.info("No entities to display.")
        return

    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        show_inferred = st.checkbox("Show inferred entities", value=True)
    with col2:
        show_reports  = st.checkbox("Show report nodes", value=False)
    with col3:
        st.markdown("🖱️ Drag · Scroll to zoom · Hover for details")

    nodes, edges = _build_graph_data(result, show_inferred, show_reports)

    if not nodes:
        st.info("No nodes to display with current filter settings.")
        return

    c1, c2, c3 = st.columns(3)
    with c1: st.metric("Nodes", len(nodes))
    with c2: st.metric("Edges", len(edges))
    with c3:
        inferred_count = sum(1 for e in result.get("entities",[]) if e.get("inferred") and
                             (show_inferred) and (show_reports or e.get("type") != "report"))
        st.metric("Inferred", inferred_count)

    html = _build_html(nodes, edges, height=height)
    components.html(html, height=height + 20, scrolling=False)