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
  duration: number;
  delay: number;
  min: number;
  max: number;
}

interface OrbitBand {
  rMin: number;
  rMax: number;
  count: number;
  spinDuration: number;
  reverse: boolean;
  colors: string[];
}

function seededRand(seed: number): () => number {
  let s = seed || 1;
  return () => {
    s = (s * 1103515245 + 12345) & 0x7fffffff;
    return (s % 10000) / 10000;
  };
}

// Densidad de "polvo de datos" radial: más denso y cálido cerca del núcleo,
// más disperso y frío hacia el borde — el mismo patrón de caída de densidad
// de un radar/campo orbital real en vez de puntos repartidos uniformemente
// (uniforme se lee como "decoración plana"; con caída de densidad se lee
// como estructura con centro de gravedad).
function makeOrbitBands(cx: number, cy: number, maxR: number): (OrbitBand & { particles: Particle[] })[] {
  const defs: OrbitBand[] = [
    { rMin: 16, rMax: maxR * 0.32, count: 90, spinDuration: 34000, reverse: false,
      colors: ["var(--ember)", "var(--ember-2)", "var(--accent)"] },
    { rMin: maxR * 0.32, rMax: maxR * 0.6, count: 70, spinDuration: 58000, reverse: true,
      colors: ["var(--accent)", "var(--accent-2)", "var(--ember-2)"] },
    { rMin: maxR * 0.6, rMax: maxR * 0.85, count: 46, spinDuration: 86000, reverse: false,
      colors: ["var(--accent-2)", "var(--text-dim)", "var(--accent)"] },
    { rMin: maxR * 0.85, rMax: maxR * 1.05, count: 26, spinDuration: 120000, reverse: true,
      colors: ["var(--text-dim)", "var(--accent-2)"] },
  ];
  const rand = seededRand(cx * 7 + cy * 13 + 91);
  let pid = 0;
  return defs.map((band) => ({
    ...band,
    particles: Array.from({ length: band.count }, () => {
      const angle = rand() * Math.PI * 2;
      const radius = Math.sqrt(rand() * (band.rMax ** 2 - band.rMin ** 2) + band.rMin ** 2);
      return {
        id: pid++,
        x: cx + Math.cos(angle) * radius,
        y: cy + Math.sin(angle) * radius,
        r: 0.5 + rand() * 1.7,
        color: band.colors[Math.floor(rand() * band.colors.length)],
        duration: 2600 + rand() * 4200,
        delay: rand() * 4000,
        min: 0.05 + rand() * 0.12,
        max: 0.35 + rand() * 0.45,
      };
    }),
  }));
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

  const orbitBands = useMemo(
    () => makeOrbitBands(cx, cy, Math.min(size.w, size.h) / 2 - 10),
    [cx, cy],
  );

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
  const maxRing = Math.max(0, ...Array.from(rings.values()));

  return (
    <div style={{ position: "relative", flex: 1, minHeight: 0 }}>
      <svg
        ref={ref}
        viewBox={`0 0 ${size.w} ${size.h}`}
        style={{ width: "100%", height: "100%" }}
      >
        <defs>
          <filter id="atlas-glow" x="-150%" y="-150%" width="400%" height="400%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="atlas-glow-soft" x="-200%" y="-200%" width="500%" height="500%">
            <feGaussianBlur stdDeviation="14" />
          </filter>
          <radialGradient id="atlas-core-grad">
            <stop offset="0%" stopColor="#eafcff" stopOpacity="0.95" />
            <stop offset="18%" stopColor="var(--accent)" stopOpacity="0.75" />
            <stop offset="55%" stopColor="var(--accent)" stopOpacity="0.2" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* Atmósfera: núcleo caliente con bloom + bandas orbitales de polvo
            de datos (densas y cálidas cerca del centro, dispersas y frías
            hacia el borde) girando a velocidades distintas + anillos de
            radar. Decoración honesta (nunca representa datos que no
            existen) — le da al panel la densidad y profundidad de un campo
            vivo en vez de un puñado de puntos sueltos. */}
        <g className="graph-atmosphere">
          <circle
            className="graph-core-bloom"
            cx={cx}
            cy={cy}
            r={130}
            fill="url(#atlas-core-grad)"
          />
          <circle
            className="graph-core-hot"
            cx={cx}
            cy={cy}
            r={7}
            fill="#eafcff"
            filter="url(#atlas-glow)"
          />
          {Array.from({ length: Math.max(3, maxRing + 1) }, (_, i) => i + 1).map(
            (i) => (
              <circle
                key={i}
                className={`graph-ring spin-${["a", "b", "c"][i % 3]}`}
                cx={cx}
                cy={cy}
                r={i * RING_STEP}
                strokeDasharray={i % 2 === 0 ? "1 7" : "3 10"}
              />
            ),
          )}
          {orbitBands.map((band, bi) => (
            <g
              key={bi}
              className="graph-orbit"
              style={{
                transformOrigin: `${cx}px ${cy}px`,
                animationDuration: `${band.spinDuration}ms`,
                animationDirection: band.reverse ? "reverse" : "normal",
              }}
            >
              {band.particles.map((p) => (
                <circle
                  key={p.id}
                  className="graph-particle"
                  cx={p.x}
                  cy={p.y}
                  r={p.r}
                  fill={p.color}
                  style={
                    {
                      animationDuration: `${p.duration}ms`,
                      animationDelay: `${p.delay}ms`,
                      "--tw-min": p.min,
                      "--tw-max": p.max,
                    } as React.CSSProperties
                  }
                />
              ))}
            </g>
          ))}
        </g>

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
          const r = 9 + n.activity * 13;
          const color = NODE_COLORS[n.type] ?? "var(--text-dim)";
          const live = byId.get(n.id);
          const running = n.state === "running";
          const hot = n.activity > 0.2 || running;
          const delay = delayFor(n.id);
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
              {hot && (
                <circle
                  className="halo"
                  r={r + 10}
                  fill={color}
                  filter="url(#atlas-glow)"
                  style={{ animationDelay: `${delay}ms` }}
                />
              )}
              <circle
                className="core"
                r={r}
                fill={color}
                opacity={0.3 + n.activity * 0.65}
                stroke={running ? color : "transparent"}
                strokeWidth={2.5}
                style={{ animationDelay: `${delay}ms` }}
              />
              <circle r={3.5} fill={color} />
              <text className="graph-label" y={r + 13} textAnchor="middle">
                {n.label}
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
