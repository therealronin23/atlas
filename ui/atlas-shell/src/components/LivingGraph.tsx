// Living Knowledge Graph v2: SVG + d3-force (ADR-059), con presencia real —
// respira, brilla y hace fluir energía por las aristas activas en vez de
// congelarse en cuanto la simulación de layout se asienta. Los eventos
// iluminan la actividad de los nodos; click → inspector.

import { useEffect, useMemo, useRef, useState } from "react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
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
}

interface Props {
  graph: GraphData | null;
  onSelect: (node: GraphNode) => void;
}

// Retraso de animación determinista por nodo — así cada uno respira a su
// propio ritmo en vez de pulsar todos al unísono (se sentiría mecánico).
function delayFor(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return h % 4200;
}

export function LivingGraph({ graph, onSelect }: Props) {
  const ref = useRef<SVGSVGElement>(null);
  const [positions, setPositions] = useState<Map<string, { x: number; y: number }>>(
    new Map(),
  );
  const size = { w: 640, h: 420 };

  const simNodes = useMemo<SimNode[]>(
    () => (graph?.nodes ?? []).map((node) => ({ node })),
    [graph?.nodes.length],
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
      .force("charge", forceManyBody().strength(-320))
      .force("link", forceLink(links).distance(110))
      .force("center", forceCenter(size.w / 2, size.h / 2))
      .force("collide", forceCollide(34))
      .on("tick", () => {
        setPositions(
          new Map(
            simNodes.map((n) => [
              n.node.id,
              { x: n.x ?? size.w / 2, y: n.y ?? size.h / 2 },
            ]),
          ),
        );
      });
    return () => void sim.stop();
  }, [simNodes]);

  if (!graph) {
    return <div className="body">Sin grafo: bridge no disponible.</div>;
  }

  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const cx = size.w / 2;
  const cy = size.h / 2;

  return (
    <div style={{ position: "relative", flex: 1, minHeight: 0 }}>
      <svg
        ref={ref}
        viewBox={`0 0 ${size.w} ${size.h}`}
        style={{ width: "100%", height: "100%" }}
      >
        <defs>
          <filter id="atlas-glow" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Atmósfera: anillos de radar + barrido rotatorio — el fondo del
            grafo nunca es un vacío estático, siempre hay una señal viva. */}
        <g className="graph-atmosphere">
          {[70, 140, 210].map((r) => (
            <circle key={r} className="graph-ring" cx={cx} cy={cy} r={r} />
          ))}
          <g className="graph-sweep" style={{ transformOrigin: `${cx}px ${cy}px` }}>
            <path
              d={`M ${cx} ${cy} L ${cx + 210} ${cy} A 210 210 0 0 1 ${
                cx + 210 * Math.cos(Math.PI / 6)
              } ${cy - 210 * Math.sin(Math.PI / 6)} Z`}
              fill="url(#atlas-sweep-grad)"
            />
          </g>
          <defs>
            <linearGradient id="atlas-sweep-grad" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.14" />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
            </linearGradient>
          </defs>
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
            <line
              key={e.id}
              className={`graph-edge${active ? " is-active" : ""}`}
              x1={s.x}
              y1={s.y}
              x2={t.x}
              y2={t.y}
              style={active ? { stroke: flowColor, opacity: 0.75 } : undefined}
            />
          );
        })}
        {graph.nodes.map((n) => {
          const p = positions.get(n.id);
          if (!p) return null;
          const r = 10 + n.activity * 14;
          const color = NODE_COLORS[n.type] ?? "var(--text-dim)";
          const live = byId.get(n.id);
          const running = n.state === "running";
          const delay = delayFor(n.id);
          return (
            <g
              key={n.id}
              className={`graph-node${running ? " is-running" : ""}`}
              transform={`translate(${p.x},${p.y})`}
              style={{ cursor: "pointer" }}
              onClick={() => live && onSelect(live)}
            >
              {(running || n.activity > 0.2) && (
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
                opacity={0.28 + n.activity * 0.7}
                stroke={running ? color : "transparent"}
                strokeWidth={2.5}
                style={{ animationDelay: `${delay}ms` }}
              />
              <circle r={4} fill={color} />
              <text y={r + 13} textAnchor="middle">
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
