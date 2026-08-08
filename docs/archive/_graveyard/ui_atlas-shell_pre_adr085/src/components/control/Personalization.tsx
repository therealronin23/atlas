// Personalización con efecto REAL: cada control cambia comportamiento
// observable (tema, densidad, animación, confirmación, filtros del timeline).

import type { Preferences, Risk } from "../../core/types";
import { RISK_ORDER } from "../../core/types";

interface Props {
  prefs: Preferences;
  onChange: (p: Preferences) => void;
}

export function Personalization({ prefs, onChange }: Props) {
  const set = <K extends keyof Preferences>(key: K, value: Preferences[K]) =>
    onChange({ ...prefs, [key]: value });

  return (
    <div className="body">
      <div className="settings-row">
        <div>
          <div>Tema</div>
          <div className="hint">Aplica al instante vía data-theme en el documento.</div>
        </div>
        <select value={prefs.theme} onChange={(e) => set("theme", e.target.value as Preferences["theme"])}>
          <option value="dark">Oscuro</option>
          <option value="light">Claro</option>
        </select>
      </div>
      <div className="settings-row">
        <div>
          <div>Densidad</div>
          <div className="hint">Compact reduce paddings y tipografía en toda la shell.</div>
        </div>
        <select value={prefs.density} onChange={(e) => set("density", e.target.value as Preferences["density"])}>
          <option value="comfortable">Cómoda</option>
          <option value="compact">Compacta</option>
        </select>
      </div>
      <div className="settings-row">
        <div>
          <div>Animaciones</div>
          <div className="hint">Off desactiva pulsos y transiciones (CSS real, no cosmético).</div>
        </div>
        <input
          type="checkbox"
          checked={prefs.animations}
          onChange={(e) => set("animations", e.target.checked)}
        />
      </div>
      <div className="settings-row">
        <div>
          <div>Confirmar antes de ejecutar intención</div>
          <div className="hint">
            Política de confirmación: con esto activo, la Universal Bar pide
            confirmación antes de POST /intent.
          </div>
        </div>
        <input
          type="checkbox"
          checked={prefs.confirmBeforeIntent}
          onChange={(e) => set("confirmBeforeIntent", e.target.checked)}
        />
      </div>
      <div className="settings-row">
        <div>
          <div>Riesgo mínimo visible en timeline</div>
          <div className="hint">Filtra el timeline de verdad (tolerancia al ruido).</div>
        </div>
        <select
          value={prefs.minRiskShown}
          onChange={(e) => set("minRiskShown", e.target.value as Risk)}
        >
          {RISK_ORDER.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </div>
      <div className="settings-row">
        <div>
          <div>Mostrar eventos simulados</div>
          <div className="hint">Off deja solo lo REAL en el timeline.</div>
        </div>
        <input
          type="checkbox"
          checked={prefs.showSimulated}
          onChange={(e) => set("showSimulated", e.target.checked)}
        />
      </div>
    </div>
  );
}
