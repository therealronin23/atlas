// Developer Event Inspector: el evento crudo, sin esconder nada.

import type { GraphNode, OsEvent } from "../core/types";

interface Props {
  event: OsEvent | null;
  node: GraphNode | null;
}

export function EventInspector({ event, node }: Props) {
  const value = event ?? node;
  return (
    <div className="body">
      {!value && (
        <div style={{ color: "var(--text-dim)" }}>
          Click en un evento del timeline o un nodo del grafo.
        </div>
      )}
      {value && (
        <pre className="inspector">{JSON.stringify(value, null, 2)}</pre>
      )}
    </div>
  );
}
