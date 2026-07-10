// Living Knowledge Graph v1: SVG + d3-force (ADR-059). Los eventos iluminan
// la actividad de los nodos; click → inspector.

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
  user: "#5aa9ff",
  memory: "#9d7bff",
  tool: "#4ade80",
  process: "#fbbf24",
  runtime: "#38bdf8",
  project: "#f472b6",
  artifact: "#a3e635",
  connector: "#fb923c",
  error: "#f87171",
};

interface SimNode extends SimulationNodeDatum {
  node: GraphNode;
}

interface Props {
  graph: GraphData | null;
  onSelect: (node: GraphNode) => void;
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

  return (
    <div style={{ position: "relative", flex: 1, minHeight: 0 }}>
      <svg
        ref={ref}
        viewBox={`0 0 ${size.w} ${size.h}`}
        style={{ width: "100%", height: "100%" }}
      >
        {graph.edges.map((e) => {
          const s = positions.get(e.source);
          const t = positions.get(e.target);
          if (!s || !t) return null;
          return (
            <line key={e.id} className="graph-edge" x1={s.x} y1={s.y} x2={t.x} y2={t.y} />
          );
        })}
        {graph.nodes.map((n) => {
          const p = positions.get(n.id);
          if (!p) return null;
          const r = 10 + n.activity * 14;
          const color = NODE_COLORS[n.type] ?? "#8a93a8";
          const live = byId.get(n.id);
          return (
            <g
              key={n.id}
              className="graph-node"
              transform={`translate(${p.x},${p.y})`}
              style={{ cursor: "pointer" }}
              onClick={() => live && onSelect(live)}
            >
              <circle
                r={r}
                fill={color}
                opacity={0.28 + n.activity * 0.7}
                stroke={n.state === "running" ? color : "transparent"}
                strokeWidth={2.5}
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
