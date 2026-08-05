// Universal Bar: intención → POST /intent (con política de confirmación real)
// + reproducción de fixtures del simulador.

import { useState } from "react";
import { api } from "../core/api";
import type { Preferences } from "../core/types";

const FIXTURES = [
  "demo_first_run",
  "demo_coding_task",
  "demo_import_conversation",
  "demo_connector_sync",
  "demo_error_and_recovery",
];

interface Props {
  prefs: Preferences;
  connected: boolean;
}

export function UniversalBar({ prefs, connected }: Props) {
  const [text, setText] = useState("");
  const [pending, setPending] = useState(false);

  const submit = async () => {
    const trimmed = text.trim();
    if (!trimmed || pending) return;
    if (
      prefs.confirmBeforeIntent &&
      !window.confirm(`¿Ejecutar intención?\n\n"${trimmed}"\n\n(pipeline simulado v1)`)
    ) {
      return;
    }
    setPending(true);
    try {
      await api.intent(trimmed);
      setText("");
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="universal-bar">
      <input
        value={text}
        disabled={!connected}
        placeholder={
          connected
            ? "Escribe una intención… (v1: pipeline simulado, marcado SIM)"
            : "Bridge no disponible — arranca `atlas os-bridge`"
        }
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && void submit()}
      />
      <button className="primary" disabled={!connected || pending} onClick={() => void submit()}>
        Ejecutar
      </button>
      <select
        disabled={!connected}
        defaultValue=""
        onChange={(e) => {
          if (e.target.value) {
            void api.simulate(e.target.value);
            e.target.value = "";
          }
        }}
      >
        <option value="" disabled>
          ▶ fixture…
        </option>
        {FIXTURES.map((f) => (
          <option key={f} value={f}>
            {f}
          </option>
        ))}
      </select>
    </div>
  );
}
