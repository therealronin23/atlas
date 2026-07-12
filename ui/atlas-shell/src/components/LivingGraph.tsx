// Living Knowledge Graph v3: d3-force + layout radial (no un blob generico
// de nodos-y-lineas). Un núcleo (el nodo de mayor grado real) ancla el
// centro; el resto se organiza en anillos por distancia real de saltos
// (BFS sobre las aristas), como un radar orbital — no decoración: la
// geometría representa la estructura real del grafo. Aristas curvas tipo
// traza de circuito, campo de partículas ambientales de fondo, anillos de
// radar a velocidades distintas, núcleo con bloom pulsante. Los eventos
// siguen iluminando actividad real; click → inspector.

import { useEffect, useMemo, useRef, useState } from "react";
import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceRadial,
  forceSimulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import type { GraphData, GraphNode } from "../core/types";

const NODE_COLORS: Record<string, string> = {
  user: "var(--accent)",
  memory: "var(--accent-2)",
  tool: "var(--ok)",
  process: "var(--warn)",
  runtime: "#38bdf8",
  project: "#f472b6",
  artifact: "#a3e635",
  connector: "#fb923c",
  error: "var(--danger)",
};

interface SimNode extends SimulationNodeDatum {
  node: GraphNode;
  ring: number;
}

interface Props {
  graph: GraphData | null;
  onSelect: (node: GraphNode) => void;
}

function delayFor(id: string, mod = 4200): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return h % mod;
}

// BFS real sobre las aristas: distancia en saltos desde el núcleo (el nodo
// de mayor grado). Determina el anillo — geometría con significado, no
// posiciones aleatorias con apariencia de radar.
function ringsFromCore(nodes: GraphNode[], edges: GraphData["edges"]): Map<string, number> {
  const degree = new Map<string, number>();
  const adj = new Map<string, string[]>();
  for (const n of nodes) {
    degree.set(n.id, 0);
    adj.set(n.id, []);
  }
  for (const e of edges) {
    if (!adj.has(e.source) || !adj.has(e.target)) continue;
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
    adj.get(e.source)!.push(e.target);
    adj.get(e.target)!.push(e.source);
  }
  let core = nodes[0]?.id;
  let best = -1;
  for (const n of nodes) {
    const d = degree.get(n.id) ?? 0;
    if (d > best) {
      best = d;
      core = n.id;
    }
  }
  const rings = new Map<string, number>();
  if (core === undefined) return rings;
  rings.set(core, 0);
  const queue = [core];
  while (queue.length) {
    const cur = queue.shift()!;
    const curRing = rings.get(cur)!;
    for (const next of adj.get(cur) ?? []) {
      if (rings.has(next)) continue;
      rings.set(next, curRing + 1);
      queue.push(next);
    }
  }
  const maxRing = Math.max(0, ...rings.values());
  for (const n of nodes) {
    if (!rings.has(n.id)) rings.set(n.id, maxRing + 1);
  }
  return rings;
}

interface Particle {
  id: number;
  x: number;
  y: number;
  r: number;
  color: string;
  opacity: number;
  twinkle: boolean;
  duration: number;
  delay: number;
}

interface Filament {
  id: number;
  angle: number;
  rInner: number;
  rOuter: number;
  color: string;
  opacity: number;
  width: number;
}

interface Field {
  particles: Particle[];
  filaments: Filament[];
}

function seededRand(seed: number): () => number {
  let s = seed || 1;
  return () => {
    s = (s * 1103515245 + 12345) & 0x7fffffff;
    return (s % 10000) / 10000;
  };
}

// Interpola por t∈[0,1] a lo largo de una rampa cálida→fría (núcleo caliente
// blanco-cian → ámbar → violeta en el borde), como la referencia HUD del
// operador. Devuelve una CSS var o color literal.
function fieldColor(t: number, rand: () => number): string {
  // t=0 centro, t=1 borde. Mezcla con algo de ruido para que no sea bandas.
  const j = t + (rand() - 0.5) * 0.18;
  if (j < 0.18) return "#eafcff";
  if (j < 0.42) return "var(--accent)";
  if (j < 0.66) return "var(--ember-2)";
  if (j < 0.85) return "var(--ember)";
  return "var(--accent-2)";
}

// Campo de "polvo de datos" DENSO y LUMINOSO: ~640 partículas con densidad
// que pica a media distancia (como un disco galáctico, no un scatter plano)
// + filamentos radiales finos que dan la estructura de spokes de un radar
// real. Decoración honesta (nunca representa datos que no existen) — su
// trabajo es dar masa, profundidad y vida, con el grafo real encima. El
// campo entero rota lento como un solo cuerpo; solo un subconjunto titila
// (600 animaciones CSS = jank; rotación de grupo + titileo parcial = vivo y
// barato).
function makeField(cx: number, cy: number, maxR: number): Field {
  const rand = seededRand(Math.round(cx) * 7 + Math.round(cy) * 13 + 91);
  const particles: Particle[] = [];
  const COUNT = 640;
  for (let i = 0; i < COUNT; i++) {
    const angle = rand() * Math.PI * 2;
    // Densidad radial con pico a ~0.5·maxR: dos randoms sesgan hacia el
    // centro-medio; el disco se ve como masa, no como puntos uniformes.
    const bias = (rand() + rand() + rand()) / 3; // ~triangular, media 0.5
    const radius = bias * maxR;
    const t = radius / maxR;
    const jitter = 1 - t * 0.55; // más brillo cerca del centro
    particles.push({
      id: i,
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
      r: 0.35 + rand() * (1.6 - t) + (rand() < 0.04 ? 1.4 : 0),
      color: fieldColor(t, rand),
      opacity: (0.14 + rand() * 0.5) * jitter,
      twinkle: rand() < 0.12,
      duration: 2200 + rand() * 4200,
      delay: rand() * 5000,
    });
  }
  const filaments: Filament[] = [];
  const FIL = 54;
  for (let i = 0; i < FIL; i++) {
    const angle = rand() * Math.PI * 2;
    const rInner = maxR * (0.06 + rand() * 0.18);
    const rOuter = maxR * (0.5 + rand() * 0.55);
    const t = rInner / maxR;
    filaments.push({
      id: i,
      angle,
      rInner,
      rOuter,
      color: fieldColor(t, rand),
      opacity: 0.05 + rand() * 0.16,
      width: rand() < 0.2 ? 1.1 : 0.5,
    });
  }
  return { particles, filaments };
}

function curvedPath(x1: number, y1: number, x2: number, y2: number): string {
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.hypot(dx, dy) || 1;
  const bow = Math.min(len * 0.18, 26);
  const nx = -dy / len;
  const ny = dx / len;
  const cx = mx + nx * bow;
  const cy = my + ny * bow;
  return `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;
}

export function LivingGraph({ graph, onSelect }: Props) {
  const ref = useRef<SVGSVGElement>(null);
  const [positions, setPositions] = useState<Map<string, { x: number; y: number }>>(
    new Map(),
  );
  const size = { w: 640, h: 420 };
  const cx = size.w / 2;
  const cy = size.h / 2;
  const RING_STEP = 62;

  const rings = useMemo(
    () => (graph ? ringsFromCore(graph.nodes, graph.edges) : new Map<string, number>()),
    [graph],
  );

  const simNodes = useMemo<SimNode[]>(
    () =>
      (graph?.nodes ?? []).map((node) => ({
        node,
        ring: rings.get(node.id) ?? 0,
      })),
    [graph?.nodes.length, rings],
  );

  const maxFieldR = Math.min(size.w, size.h) / 2 + 6;
  const field = useMemo(() => makeField(cx, cy, maxFieldR), [cx, cy, maxFieldR]);

  useEffect(() => {
    if (!graph || simNodes.length === 0) return;
    const links: SimulationLinkDatum<SimNode>[] = graph.edges
      .map((e) => ({
        source: simNodes.findIndex((n) => n.node.id === e.source),
        target: simNodes.findIndex((n) => n.node.id === e.target),
      }))
      .filter((l) => (l.source as number) >= 0 && (l.target as number) >= 0);

    const sim = forceSimulation(simNodes)
      .force("charge", forceManyBody().strength(-90))
      .force("link", forceLink(links).distance(70).strength(0.25))
      .force("collide", forceCollide(30))
      .force(
        "radial",
        forceRadial<SimNode>((d) => d.ring * RING_STEP, cx, cy).strength(0.9),
      )
      .on("tick", () => {
        setPositions(
          new Map(
            simNodes.map((n) => [
              n.node.id,
              { x: n.x ?? cx, y: n.y ?? cy },
            ]),
          ),
        );
      });
    return () => void sim.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [simNodes]);

  const [hoverId, setHoverId] = useState<string | null>(null);

  if (!graph) {
    return <div className="body">Sin grafo: bridge no disponible.</div>;
  }

  const byId = new Map(graph.nodes.map((n) => [n.id, n]));

  return (
    <div style={{ position: "relative", flex: 1, minHeight: 0 }}>
      <svg
        ref={ref}
        viewBox={`0 0 ${size.w} ${size.h}`}
        preserveAspectRatio="xMidYMid slice"
        style={{ width: "100%", height: "100%", display: "block" }}
      >
        <defs>
          <filter id="atlas-glow" x="-150%" y="-150%" width="400%" height="400%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="atlas-field-bloom" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="2.4" />
          </filter>
          <radialGradient id="atlas-core-grad">
            <stop offset="0%" stopColor="#eafcff" stopOpacity="0.95" />
            <stop offset="14%" stopColor="var(--accent)" stopOpacity="0.7" />
            <stop offset="42%" stopColor="var(--ember-2)" stopOpacity="0.22" />
            <stop offset="72%" stopColor="var(--ember)" stopOpacity="0.08" />
            <stop offset="100%" stopColor="var(--accent-2)" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="atlas-vignette">
            <stop offset="55%" stopColor="#000" stopOpacity="0" />
            <stop offset="100%" stopColor="#000" stopOpacity="0.55" />
          </radialGradient>
        </defs>

        {/* Campo vivo: bloom del núcleo + disco denso de polvo de datos con
            filamentos radiales, rotando lento como un solo cuerpo. Decoración
            honesta (jamás representa datos que no existen) — su trabajo es
            dar masa, profundidad y vida; el grafo real (7 nodos, 5 aristas)
            va encima, brillante y etiquetado, como el dato de verdad. */}
        <circle cx={cx} cy={cy} r={maxFieldR} fill="url(#atlas-core-grad)" className="graph-core-bloom" />

        <g
          className="graph-field"
          style={{ transformOrigin: `${cx}px ${cy}px` }}
        >
          {/* Filamentos radiales — la estructura de "spokes" del campo.
              Sin filtro SVG: el desenfoque por-elemento sobre cientos de
              nodos animados hunde el framerate (medido). La luminosidad la
              da el gradiente del núcleo + la densidad, no un blur caro. */}
          {field.filaments.map((f) => (
            <line
              key={`f${f.id}`}
              x1={cx + Math.cos(f.angle) * f.rInner}
              y1={cy + Math.sin(f.angle) * f.rInner}
              x2={cx + Math.cos(f.angle) * f.rOuter}
              y2={cy + Math.sin(f.angle) * f.rOuter}
              stroke={f.color}
              strokeWidth={f.width}
              strokeOpacity={f.opacity}
              strokeLinecap="round"
            />
          ))}
          {/* Polvo denso — capa base, crisp (sin filtro). */}
          {field.particles.map((p) => (
            <circle
              key={p.id}
              className={p.twinkle ? "graph-particle" : undefined}
              cx={p.x}
              cy={p.y}
              r={p.r}
              fill={p.color}
              opacity={p.opacity}
              style={
                p.twinkle
                  ? ({
                      animationDuration: `${p.duration}ms`,
                      animationDelay: `${p.delay}ms`,
                      "--tw-min": p.opacity * 0.4,
                      "--tw-max": Math.min(1, p.opacity * 2.2),
                    } as React.CSSProperties)
                  : undefined
              }
            />
          ))}
        </g>

        {/* Anillos de escala tenues + núcleo caliente. */}
        {[0.32, 0.62, 0.92].map((f, i) => (
          <circle
            key={i}
            className={`graph-ring spin-${["a", "b", "c"][i % 3]}`}
            cx={cx}
            cy={cy}
            r={maxFieldR * f}
            strokeDasharray={i % 2 === 0 ? "1 9" : "2 12"}
          />
        ))}
        <circle
          className="graph-core-hot"
          cx={cx}
          cy={cy}
          r={6}
          fill="#eafcff"
          filter="url(#atlas-glow)"
        />
        <rect x={0} y={0} width={size.w} height={size.h} fill="url(#atlas-vignette)" pointerEvents="none" />

        {graph.edges.map((e) => {
          const s = positions.get(e.source);
          const t = positions.get(e.target);
          if (!s || !t) return null;
          const sNode = byId.get(e.source);
          const tNode = byId.get(e.target);
          const active =
            (sNode && (sNode.activity > 0.15 || sNode.state === "running")) ||
            (tNode && (tNode.activity > 0.15 || tNode.state === "running"));
          const flowColor = active
            ? NODE_COLORS[(sNode ?? tNode)?.type ?? ""] ?? "var(--accent)"
            : undefined;
          return (
            <path
              key={e.id}
              className={`graph-edge graph-edge-path${active ? " is-active" : ""}`}
              d={curvedPath(s.x, s.y, t.x, t.y)}
              style={active ? { stroke: flowColor, opacity: 0.8 } : undefined}
            />
          );
        })}
        {graph.nodes.map((n) => {
          const p = positions.get(n.id);
          if (!p) return null;
          const r = 8 + n.activity * 10;
          const color = NODE_COLORS[n.type] ?? "var(--text-dim)";
          const live = byId.get(n.id);
          const running = n.state === "running";
          const delay = delayFor(n.id);
          const label = n.label.length > 16 ? `${n.label.slice(0, 15)}…` : n.label;
          return (
            <g
              key={n.id}
              className={`graph-node${running ? " is-running" : ""}${
                hoverId === n.id ? " is-hot" : ""
              }`}
              transform={`translate(${p.x},${p.y})`}
              style={{ cursor: "pointer" }}
              onClick={() => live && onSelect(live)}
              onMouseEnter={() => setHoverId(n.id)}
              onMouseLeave={() => setHoverId((id) => (id === n.id ? null : id))}
            >
              {/* Halo con glow — el nodo real destaca sobre el campo denso. */}
              <circle
                className="halo"
                r={r + 12}
                fill={color}
                filter="url(#atlas-glow)"
                style={{ animationDelay: `${delay}ms` }}
              />
              {/* Backing oscuro: recorta el campo detrás para que el nodo lea
                  como sólido, no translúcido sobre el polvo. */}
              <circle r={r + 2} fill="var(--bg)" opacity={0.82} />
              <circle
                className="core"
                r={r}
                fill={color}
                stroke="#eafcff"
                strokeOpacity={running ? 0.9 : 0.4}
                strokeWidth={running ? 2 : 1}
                style={{ animationDelay: `${delay}ms` }}
              />
              <circle r={r * 0.4} fill="#eafcff" opacity={0.85} />
              <text className="graph-label" y={r + 14} textAnchor="middle">
                {label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function GraphLegend() {
  return (
    <div className="legend">
      {Object.entries(NODE_COLORS).map(([type, color]) => (
        <span key={type} style={{ "--node-color": color } as React.CSSProperties}>
          {type}
        </span>
      ))}
    </div>
  );
}
