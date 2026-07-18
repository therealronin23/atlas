// Atlas Nebula — el Living Knowledge Graph como organismo 3D real.
//
// Cada punto es un FICHERO real del grafo de dependencias (graphify:
// 4206 nodos, 10485 aristas), maquetado por comunidad y coloreado por
// módulo con la gramática semántica del repo. No es decoración: la
// geometría es la estructura real de Atlas. Se orbita (arrastrar), se
// acerca (rueda), y REACCIONA a los eventos reales del bridge — cada
// acción del daemon enciende su hub, lanza tokens por dependencias
// reales y pulsa el reactor, con audio cinematográfico reactivo.
//
// Motor: three (WebGL, additive glow, curl-noise drift). Portado del
// spike de dirección de arte ya aprobado ("guau" del operador), ahora
// como componente vivo dentro del shell real.

import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import * as THREE from "three";
import type { OsEvent } from "../core/types";

export interface NebulaMode {
  mode: "command" | "exec" | "memory";
}

export interface NebulaHandle {
  react: (event: OsEvent) => void;
  setMode: (mode: NebulaMode["mode"]) => void;
  think: () => void;
}

interface Props {
  onPick?: (node: NodePick) => void;
  onHealth?: (health: GraphHealth) => void;
  onActivity?: (event: OsEvent) => void;
  soundDefault?: boolean;
}

interface BakedGraph {
  colors: string[];
  X: number[];
  Y: number[];
  COL: number[];
  SZ: number[];
  L: [number, number, number][];
  hubs: { i: number; label: string; mod: string }[];
  legend: { m: string; c: string; n: number }[];
  n: number;
  m: number;
  // Añadidos 2026-07-18: identidad real por nodo (arreglo de la queja "es
  // decorativo, no tiene descripción") — cada uno de los N puntos es un
  // fichero real del repo, no decoración.
  labels: string[];
  files: string[];
  deg: number[];
  orphans: number[];
  edgeRel: Record<string, string>;
  relTypes: Record<string, number>;
}

export interface GraphHealth {
  total: number;
  orphanCount: number;
  orphanFiles: { label: string; file: string }[];
  edgeCount: number;
  relTypes: Record<string, number>;
}

export interface NodePick {
  label: string;
  file: string;
  mod: string;
  deg: number;
  orphan: boolean;
  color: string;
  merkle: string;
  connections: { label: string; relation: string }[];
}

// simplex 3D (Gustavson), inline — drift orgánico barato en CPU.
const grad3 = new Float32Array([
  1, 1, 0, -1, 1, 0, 1, -1, 0, -1, -1, 0, 1, 0, 1, -1, 0, 1, 1, 0, -1, -1, 0,
  -1, 0, 1, 1, 0, -1, 1, 0, 1, -1, 0, -1, -1,
]);
const perm = new Uint8Array(512);
{
  const p0 = new Uint8Array(256);
  for (let i = 0; i < 256; i++) p0[i] = i;
  let n = 256;
  let s = 1234;
  const r = () => {
    s = (s * 16807) % 2147483647;
    return s / 2147483647;
  };
  while (n > 1) {
    const k = (r() * n) | 0;
    n--;
    const t = p0[n];
    p0[n] = p0[k];
    p0[k] = t;
  }
  for (let i = 0; i < 512; i++) perm[i] = p0[i & 255];
}
function sn3(x: number, y: number, z: number): number {
  const F3 = 1 / 3,
    G3 = 1 / 6;
  const s = (x + y + z) * F3;
  const i = Math.floor(x + s),
    j = Math.floor(y + s),
    k = Math.floor(z + s);
  const t = (i + j + k) * G3;
  const X0 = i - t,
    Y0 = j - t,
    Z0 = k - t;
  const x0 = x - X0,
    y0 = y - Y0,
    z0 = z - Z0;
  let i1, j1, k1, i2, j2, k2;
  if (x0 >= y0) {
    if (y0 >= z0) {
      i1 = 1; j1 = 0; k1 = 0; i2 = 1; j2 = 1; k2 = 0;
    } else if (x0 >= z0) {
      i1 = 1; j1 = 0; k1 = 0; i2 = 1; j2 = 0; k2 = 1;
    } else {
      i1 = 0; j1 = 0; k1 = 1; i2 = 1; j2 = 0; k2 = 1;
    }
  } else {
    if (y0 < z0) {
      i1 = 0; j1 = 0; k1 = 1; i2 = 0; j2 = 1; k2 = 1;
    } else if (x0 < z0) {
      i1 = 0; j1 = 1; k1 = 0; i2 = 0; j2 = 1; k2 = 1;
    } else {
      i1 = 0; j1 = 1; k1 = 0; i2 = 1; j2 = 1; k2 = 0;
    }
  }
  const x1 = x0 - i1 + G3, y1 = y0 - j1 + G3, z1 = z0 - k1 + G3;
  const x2 = x0 - i2 + 2 * G3, y2 = y0 - j2 + 2 * G3, z2 = z0 - k2 + 2 * G3;
  const x3 = x0 - 1 + 3 * G3, y3 = y0 - 1 + 3 * G3, z3 = z0 - 1 + 3 * G3;
  const ii = i & 255, jj = j & 255, kk = k & 255;
  let n0 = 0, n1 = 0, n2 = 0, n3 = 0;
  let t0 = 0.6 - x0 * x0 - y0 * y0 - z0 * z0;
  if (t0 > 0) {
    const gi = (perm[ii + perm[jj + perm[kk]]] % 12) * 3;
    t0 *= t0;
    n0 = t0 * t0 * (grad3[gi] * x0 + grad3[gi + 1] * y0 + grad3[gi + 2] * z0);
  }
  let t1 = 0.6 - x1 * x1 - y1 * y1 - z1 * z1;
  if (t1 > 0) {
    const gi = (perm[ii + i1 + perm[jj + j1 + perm[kk + k1]]] % 12) * 3;
    t1 *= t1;
    n1 = t1 * t1 * (grad3[gi] * x1 + grad3[gi + 1] * y1 + grad3[gi + 2] * z1);
  }
  let t2 = 0.6 - x2 * x2 - y2 * y2 - z2 * z2;
  if (t2 > 0) {
    const gi = (perm[ii + i2 + perm[jj + j2 + perm[kk + k2]]] % 12) * 3;
    t2 *= t2;
    n2 = t2 * t2 * (grad3[gi] * x2 + grad3[gi + 1] * y2 + grad3[gi + 2] * z2);
  }
  let t3 = 0.6 - x3 * x3 - y3 * y3 - z3 * z3;
  if (t3 > 0) {
    const gi = (perm[ii + 1 + perm[jj + 1 + perm[kk + 1]]] % 12) * 3;
    t3 *= t3;
    n3 = t3 * t3 * (grad3[gi] * x3 + grad3[gi + 1] * y3 + grad3[gi + 2] * z3);
  }
  return 32 * (n0 + n1 + n2 + n3);
}

// Mapea el estado de un evento real → una reacción (color + sonido).
function reactionFor(ev: OsEvent): { sfx: string; tone: number } {
  if (ev.status === "failed" || ev.risk === "critical") return { sfx: "error", tone: 0 };
  if (ev.status === "completed") return { sfx: "success", tone: 0 };
  if (ev.status === "waiting_user" || ev.risk === "high") return { sfx: "surface", tone: 0 };
  return { sfx: "synapse", tone: (ev.summary.length + ev.type.length) % 6 };
}

export const NebulaGraph = forwardRef<NebulaHandle, Props>(function NebulaGraph(
  { onPick, onHealth, onActivity, soundDefault = false },
  ref,
) {
  const mountRef = useRef<HTMLDivElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const handleRef = useRef<NebulaHandle | null>(null);

  useImperativeHandle(ref, () => ({
    react: (e) => handleRef.current?.react(e),
    setMode: (m) => handleRef.current?.setMode(m),
    think: () => handleRef.current?.think(),
  }));

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    let disposed = false;
    let raf = 0;

    const canvas = document.createElement("canvas");
    canvas.style.cssText = "width:100%;height:100%;display:block;cursor:grab;touch-action:none";
    mount.appendChild(canvas);

    const renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
    });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setClearColor(0x05070c, 1);
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x05070c, 0.0016);
    const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 3000);
    const reduce = matchMedia("(prefers-reduced-motion:reduce)").matches;

    // Estado mutable de la escena (se rellena tras cargar el grafo).
    let started = false;
    let N = 0;
    let base = new Float32Array(0);
    let pos = new Float32Array(0);
    let brightArr = new Float32Array(0);
    let target = new Float32Array(0);
    let memTarget = new Float32Array(0);
    let baseHome = new Float32Array(0);
    let adj: number[][] = [];
    let hubs: BakedGraph["hubs"] = [];
    let COL: number[] = [];
    let colorsHex: string[] = [];
    let legend: BakedGraph["legend"] = [];
    let palette: THREE.Color[] = [];
    let ng: THREE.BufferGeometry | null = null;
    let lg: THREE.BufferGeometry | null = null;
    let IL: [number, number, number][] = [];
    let linePos = new Float32Array(0);
    // Identidad REAL de cada uno de los N nodos (no solo los ~20 hubs
    // curados) — arregla "es decorativo, no tiene descripción": cualquier
    // punto es un fichero real y responde con datos reales al pincharlo.
    let labels: string[] = [];
    let files: string[] = [];
    let degArr: number[] = [];
    let orphanSet = new Set<number>();
    let edgeRel: Record<string, string> = {};
    const relLabel = (a: number, b: number) => edgeRel[`${Math.min(a, b)}-${Math.max(a, b)}`] || "conectado";
    const nodeMod = (i: number) => legend[COL[i] % legend.length]?.m ?? "?";

    // token particles
    const PN = 600;
    const pp = new Float32Array(PN * 3);
    const pc = new Float32Array(PN * 3);
    const parts: { a: number; b: number; t: number; c: THREE.Color }[] = [];
    const pg = new THREE.BufferGeometry();
    pg.setAttribute("position", new THREE.BufferAttribute(pp, 3));
    pg.setAttribute("color", new THREE.BufferAttribute(pc, 3));
    const partPts = new THREE.Points(
      pg,
      new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        vertexShader:
          "attribute vec3 color;varying vec3 vC;void main(){vC=color;vec4 mv=modelViewMatrix*vec4(position,1.);gl_PointSize=6.*(360./-mv.z);gl_Position=projectionMatrix*mv;}",
        fragmentShader:
          "varying vec3 vC;void main(){float d=length(gl_PointCoord-.5);float a=smoothstep(.5,0.,d);gl_FragColor=vec4(vC,a);}",
      }),
    );
    scene.add(partPts);
    const spawnToken = (a: number, b: number, c: THREE.Color) =>
      parts.push({ a, b, t: 0, c });

    // core reactor
    const glowTex = () => {
      const c = document.createElement("canvas");
      c.width = c.height = 128;
      const g = c.getContext("2d")!;
      const rg = g.createRadialGradient(64, 64, 0, 64, 64, 64);
      rg.addColorStop(0, "rgba(255,248,232,.75)");
      rg.addColorStop(0.12, "rgba(255,215,140,.45)");
      rg.addColorStop(0.4, "rgba(255,160,80,.14)");
      rg.addColorStop(1, "rgba(255,150,60,0)");
      g.fillStyle = rg;
      g.fillRect(0, 0, 128, 128);
      return new THREE.CanvasTexture(c);
    };
    const coreMat = new THREE.SpriteMaterial({
      map: glowTex(),
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      transparent: true,
      opacity: 0.8,
    });
    const core = new THREE.Sprite(coreMat);
    core.scale.set(24, 24, 1);
    scene.add(core);
    const coreHaloMat = new THREE.SpriteMaterial({
      map: glowTex(),
      color: 0x55d6ff,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      transparent: true,
      opacity: 0.28,
    });
    const coreHalo = new THREE.Sprite(coreHaloMat);
    coreHalo.scale.set(60, 60, 1);
    scene.add(coreHalo);

    // star dust
    const DN = 1400;
    const dp = new Float32Array(DN * 3);
    for (let i = 0; i < DN; i++) {
      const r = 300 + Math.random() * 900,
        th = Math.acos(2 * Math.random() - 1),
        ph = Math.random() * 6.28;
      dp[i * 3] = Math.sin(th) * Math.cos(ph) * r;
      dp[i * 3 + 1] = Math.sin(th) * Math.sin(ph) * r;
      dp[i * 3 + 2] = Math.cos(th) * r;
    }
    const dg = new THREE.BufferGeometry();
    dg.setAttribute("position", new THREE.BufferAttribute(dp, 3));
    const dust = new THREE.Points(
      dg,
      new THREE.PointsMaterial({
        color: 0x8fb6c0,
        size: 1.1,
        transparent: true,
        opacity: 0.24,
        depthWrite: false,
      }),
    );
    scene.add(dust);

    let points: THREE.Points | null = null;
    let lines: THREE.LineSegments | null = null;

    // ---- camera orbit ----
    let camR = 150,
      camTh = 0.6,
      camPh = 1.15,
      tR = 150,
      autorot = true,
      drag = false,
      lx = 0,
      ly = 0;
    const updateCam = () => {
      const st = Math.sin(camPh),
        x = camR * st * Math.cos(camTh),
        y = camR * Math.cos(camPh),
        z = camR * st * Math.sin(camTh);
      camera.position.set(x, y, z);
      camera.lookAt(0, 0, 0);
    };
    const onDown = (e: PointerEvent) => {
      drag = true;
      lx = e.clientX;
      ly = e.clientY;
      autorot = false;
      canvas.style.cursor = "grabbing";
      unlockAudio();
    };
    const onUp = () => {
      drag = false;
      canvas.style.cursor = "grab";
    };
    const onMove = (e: PointerEvent) => {
      if (!drag) return;
      camTh -= (e.clientX - lx) * 0.005;
      camPh = Math.max(0.2, Math.min(2.9, camPh - (e.clientY - ly) * 0.005));
      lx = e.clientX;
      ly = e.clientY;
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      tR = Math.max(70, Math.min(420, tR + e.deltaY * 0.12));
    };
    canvas.addEventListener("pointerdown", onDown);
    addEventListener("pointerup", onUp);
    addEventListener("pointermove", onMove);
    canvas.addEventListener("wheel", onWheel, { passive: false });

    // hover + click hub picking (screen space)
    const v3 = new THREE.Vector3();
    const project = (i: number): [number, number, number] => {
      v3.set(pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]).project(camera);
      const rect = canvas.getBoundingClientRect();
      return [
        (v3.x * 0.5 + 0.5) * rect.width + rect.left,
        (-v3.y * 0.5 + 0.5) * rect.height + rect.top,
        v3.z,
      ];
    };
    // Picking sobre TODOS los N nodos (no solo los ~20 hubs curados) — cada
    // uno de los 4206 puntos es un fichero real y debe responder con datos
    // reales al pasar el cursor o pinchar, no solo un puñado curado.
    const pickAt = (cx: number, cy: number, tol: number): number => {
      let bi = -1,
        bd = tol * tol;
      for (let i = 0; i < N; i++) {
        const p = project(i);
        if (p[2] > 1) continue;
        const dx = cx - p[0],
          dy = cy - p[1],
          d = dx * dx + dy * dy;
        if (d < bd) {
          bd = d;
          bi = i;
        }
      }
      return bi;
    };
    let lastHoverAt = 0;
    const onHover = (ev: MouseEvent) => {
      const tip = tipRef.current;
      if (!tip || !started) return;
      if (drag) {
        tip.style.opacity = "0";
        return;
      }
      // Throttle: escanear 4206 nodos en cada mousemove es caro: 1 vez cada
      // ~55ms basta para que la tooltip se sienta instantánea.
      const now = performance.now();
      if (now - lastHoverAt < 55) return;
      lastHoverAt = now;
      const bi = pickAt(ev.clientX, ev.clientY, 14);
      if (bi >= 0) {
        const orphan = orphanSet.has(bi);
        tip.innerHTML = `<b>${labels[bi]}</b><s>${nodeMod(bi)} · ${files[bi] || "sin ruta"}</s><s>${
          orphan
            ? '<span style="color:var(--danger)">0 conexiones — nodo huérfano</span>'
            : `${degArr[bi]} conexiones reales`
        }</s>`;
        const rect = mount.getBoundingClientRect();
        tip.style.left = ev.clientX - rect.left + 14 + "px";
        tip.style.top = ev.clientY - rect.top + 14 + "px";
        tip.style.opacity = "1";
        canvas.style.cursor = "pointer";
      } else {
        tip.style.opacity = "0";
        canvas.style.cursor = drag ? "grabbing" : "grab";
      }
    };
    addEventListener("mousemove", onHover);
    canvas.addEventListener("click", (ev) => {
      if (!started) return;
      const bi = pickAt(ev.clientX, ev.clientY, 16);
      if (bi >= 0) {
        unlockAudio();
        sfx("synapse", COL[bi]);
        flash(bi, 1.4);
        const connections = adj[bi]
          .slice(0, 8)
          .map((nb) => ({ label: labels[nb], relation: relLabel(bi, nb) }));
        onPick?.({
          label: labels[bi],
          file: files[bi] || "(sin ruta de origen registrada)",
          mod: nodeMod(bi),
          deg: degArr[bi],
          orphan: orphanSet.has(bi),
          color: colorsHex[COL[bi]],
          merkle: "",
          connections,
        });
      }
    });

    // ---- thinking traversal over real edges ----
    let thinking = false;
    const flash = (i: number, s: number) => {
      if (i < 0 || i >= N) return;
      brightArr[i] = s;
      adj[i].slice(0, 12).forEach((nb, k) =>
        setTimeout(() => {
          if (disposed) return;
          brightArr[nb] = Math.max(brightArr[nb], 1);
          spawnToken(i, nb, palette[COL[nb]]);
        }, k * 40),
      );
    };
    const think = (startHub?: number) => {
      if (thinking || !started) return;
      thinking = true;
      let cur = startHub ?? hubs[(Math.random() * hubs.length) | 0].i;
      const path = [cur];
      const seen = new Set([cur]);
      for (let h = 0; h < 7; h++) {
        const nb = adj[cur].filter((x) => !seen.has(x));
        if (!nb.length) break;
        cur = nb[(Math.random() * nb.length) | 0];
        seen.add(cur);
        path.push(cur);
      }
      let step = 0;
      const walk = () => {
        if (disposed) return;
        if (step >= path.length) {
          thinking = false;
          flash(path[path.length - 1], 1.4);
          sfx("success");
          return;
        }
        const idx = path[step];
        brightArr[idx] = 1.4;
        adj[idx].slice(0, 10).forEach((nb) => {
          if (brightArr[nb] < 0.5) brightArr[nb] = 0.6;
        });
        if (step > 0) {
          const col = palette[COL[idx]];
          for (let q = 0; q < 10; q++)
            setTimeout(() => !disposed && spawnToken(path[step - 1], idx, col), q * 24);
          sfx("synapse", COL[idx]);
        }
        step++;
        setTimeout(walk, 300 + Math.random() * 150);
      };
      walk();
    };

    // ---- morph modes ----
    let mode: NebulaMode["mode"] = "command";
    const setMode = (m: NebulaMode["mode"]) => {
      if (!started) return;
      mode = m;
      if (m === "memory") {
        target.set(memTarget);
        tR = 210;
        sfx("surface");
        waveT = 0;
      } else if (m === "exec") {
        for (let i = 0; i < N; i++) {
          const st = i % 4;
          const hxi = Math.abs(Math.sin(i * 127.1) * 43758.5) % 1;
          target[i * 3] = (st - 1.5) * 34;
          target[i * 3 + 1] = baseHome[i * 3 + 1] * 0.34 + (hxi - 0.5) * 8;
          target[i * 3 + 2] = baseHome[i * 3] * 0.34;
        }
        tR = 200;
        sfx("surface");
      } else {
        target.set(baseHome);
        tR = 150;
      }
    };
    let waveT = -1;

    // ---- react to a REAL bridge event ----
    const react = (ev: OsEvent) => {
      if (!started) return;
      onActivity?.(ev);
      const { sfx: kind, tone } = reactionFor(ev);
      // Busca un fichero REAL cuyo nombre aparezca en la fuente/tipo del
      // evento. Si no hay coincidencia real, NO se inventa un nodo al azar
      // (eso era exactamente la mentira señalada: luces sin motivo real) —
      // en su lugar solo pulsa el reactor central, que representa actividad
      // de sistema sin atribución a un fichero concreto.
      const src = ((ev.source || "") + (ev.type || "")).toLowerCase();
      let target_i = -1;
      for (let i = 0; i < N; i++) {
        const short = labels[i]?.toLowerCase().split(".")[0];
        if (short && short.length > 2 && src.includes(short)) {
          target_i = i;
          break;
        }
      }
      sfx(kind, tone);
      if (target_i >= 0) {
        if (kind === "synapse") think(target_i);
        else flash(target_i, kind === "error" ? 1.6 : 1.3);
      } else {
        // pulso genérico del núcleo — actividad real, sin fichero atribuible
        coreHaloMat.opacity = Math.min(0.55, coreHaloMat.opacity + 0.22);
      }
    };

    handleRef.current = { react, setMode, think: () => think() };

    // ---- Zimmer-style audio ----
    let AC: AudioContext | null = null;
    let master: GainNode | null = null;
    let verb: ConvolverNode | null = null;
    let drone: GainNode | null = null;
    let soundOn = soundDefault;
    let unlocked = false;
    const impulse = (sec: number, decay: number) => {
      const rate = AC!.sampleRate,
        len = rate * sec,
        buf = AC!.createBuffer(2, len, rate);
      for (let ch = 0; ch < 2; ch++) {
        const d = buf.getChannelData(ch);
        for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, decay);
      }
      return buf;
    };
    const unlockAudio = () => {
      if (unlocked) return;
      unlocked = true;
      const Ctor = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      AC = new Ctor();
      master = AC.createGain();
      master.gain.value = 0.85;
      master.connect(AC.destination);
      verb = AC.createConvolver();
      verb.buffer = impulse(3.5, 2.2);
      const vg = AC.createGain();
      vg.gain.value = 0.5;
      verb.connect(vg);
      vg.connect(master);
      drone = AC.createGain();
      drone.gain.value = 0;
      drone.connect(master);
      [27.5, 27.7, 41.2].forEach((f, i) => {
        const o = AC!.createOscillator();
        o.type = "sawtooth";
        o.frequency.value = f;
        const lp = AC!.createBiquadFilter();
        lp.type = "lowpass";
        lp.frequency.value = 140;
        const g = AC!.createGain();
        g.gain.value = i < 2 ? 0.5 : 0.3;
        o.connect(lp);
        lp.connect(g);
        g.connect(drone!);
        o.start();
      });
      const lfo = AC.createOscillator();
      lfo.frequency.value = 0.08;
      const lg2 = AC.createGain();
      lg2.gain.value = 0.4;
      lfo.connect(lg2);
      lg2.connect(drone.gain);
      lfo.start();
    };
    const setSound = (on: boolean) => {
      soundOn = on;
      if (on) {
        unlockAudio();
        if (AC && AC.state === "suspended") void AC.resume();
      }
    };
    void setSound;
    const sfx = (type: string, tone = 0) => {
      if (!soundOn || !AC || !master || !verb) return;
      const now = AC.currentTime;
      if (type === "synapse") {
        const carr = 440 * [1, 0.66, 0.75, 1.33, 1.5, 0.5][tone % 6];
        const o = AC.createOscillator();
        o.type = "sine";
        o.frequency.value = carr;
        const m = AC.createOscillator();
        m.type = "sine";
        m.frequency.value = carr * 2.01;
        const md = AC.createGain();
        md.gain.value = carr * 1.4;
        m.connect(md);
        md.connect(o.frequency);
        const g = AC.createGain();
        g.gain.value = 0;
        o.connect(g);
        g.connect(verb);
        g.connect(master);
        g.gain.setValueAtTime(0, now);
        g.gain.linearRampToValueAtTime(0.05, now + 0.005);
        g.gain.exponentialRampToValueAtTime(0.0001, now + 0.9);
        o.start(now);
        m.start(now);
        o.stop(now + 0.95);
        m.stop(now + 0.95);
      } else if (type === "success") {
        [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => {
          const o = AC!.createOscillator();
          o.type = "sine";
          o.frequency.value = f;
          const g = AC!.createGain();
          g.gain.value = 0;
          o.connect(g);
          g.connect(verb!);
          g.connect(master!);
          const st = now + (3 - i) * 0.05;
          g.gain.setValueAtTime(0, st);
          g.gain.linearRampToValueAtTime(0.05, st + 0.25);
          g.gain.exponentialRampToValueAtTime(0.0001, st + 0.9);
          o.start(st);
          o.stop(st + 1);
        });
      } else if (type === "surface") {
        [55, 82.5].forEach((f) => {
          const o = AC!.createOscillator();
          o.type = "sawtooth";
          o.frequency.value = f;
          const lp = AC!.createBiquadFilter();
          lp.type = "lowpass";
          lp.frequency.setValueAtTime(160, now);
          lp.frequency.linearRampToValueAtTime(900, now + 0.6);
          const g = AC!.createGain();
          g.gain.value = 0;
          o.connect(lp);
          lp.connect(g);
          g.connect(verb!);
          g.connect(master!);
          g.gain.setValueAtTime(0, now);
          g.gain.linearRampToValueAtTime(0.08, now + 0.15);
          g.gain.exponentialRampToValueAtTime(0.0001, now + 1.1);
          o.start(now);
          o.stop(now + 1.2);
        });
      } else if (type === "error") {
        const o = AC.createOscillator();
        o.type = "sawtooth";
        o.frequency.value = 48;
        const dist = AC.createWaveShaper();
        const cv = new Float32Array(256);
        for (let i = 0; i < 256; i++) {
          const x = i / 128 - 1;
          cv[i] = Math.tanh(x * 4);
        }
        dist.curve = cv;
        const g = AC.createGain();
        g.gain.value = 0;
        o.connect(dist);
        dist.connect(g);
        g.connect(master);
        g.gain.setValueAtTime(0, now);
        g.gain.linearRampToValueAtTime(0.14, now + 0.03);
        g.gain.exponentialRampToValueAtTime(0.0001, now + 0.6);
        o.start(now);
        o.stop(now + 0.65);
      }
    };
    // expose sound toggle on the handle lazily
    (handleRef.current as NebulaHandle & { setSound?: (on: boolean) => void }).setSound = setSound;

    // ---- resize (container, no window) ----
    const resize = () => {
      const w = mount.clientWidth || 1,
        h = mount.clientHeight || 1;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(mount);
    resize();

    // ---- build scene from the real graph ----
    const hx = (i: number) => {
      const s = Math.sin(i * 127.1) * 43758.5;
      return s - Math.floor(s);
    };
    fetch("/atlas_graph.json")
      .then((r) => r.json())
      .then((G: BakedGraph) => {
        if (disposed) return;
        N = G.n;
        COL = G.COL;
        colorsHex = G.colors;
        legend = G.legend;
        hubs = G.hubs;
        labels = G.labels;
        files = G.files;
        degArr = G.deg;
        orphanSet = new Set(G.orphans);
        edgeRel = G.edgeRel;
        palette = G.colors.map((h) => new THREE.Color(h));
        onHealth?.({
          total: G.n,
          orphanCount: G.orphans.length,
          orphanFiles: G.orphans.map((i) => ({ label: G.labels[i], file: G.files[i] || "(sin ruta)" })),
          edgeCount: G.m,
          relTypes: G.relTypes,
        });
        const SCALE = 58;
        base = new Float32Array(N * 3);
        pos = new Float32Array(N * 3);
        brightArr = new Float32Array(N);
        memTarget = new Float32Array(N * 3);
        const colArr = new Float32Array(N * 3);
        const sizeArr = new Float32Array(N);
        for (let i = 0; i < N; i++) {
          const x = G.X[i],
            y = G.Y[i];
          const r2 = x * x + y * y;
          const zc = Math.sqrt(Math.max(0, 1.18 - r2)) * (hx(i) < 0.5 ? -1 : 1) * 0.82;
          base[i * 3] = x * SCALE;
          base[i * 3 + 1] = -y * SCALE;
          base[i * 3 + 2] = zc * SCALE;
          const c = palette[G.COL[i]];
          colArr[i * 3] = c.r;
          colArr[i * 3 + 1] = c.g;
          colArr[i * 3 + 2] = c.b;
          sizeArr[i] = G.SZ[i];
          const th = Math.acos(1 - (2 * (i + 0.5)) / N),
            ph = i * 2.399963,
            R = 54 + hx(i + 7) * 10;
          memTarget[i * 3] = Math.sin(th) * Math.cos(ph) * R;
          memTarget[i * 3 + 1] = Math.sin(th) * Math.sin(ph) * R;
          memTarget[i * 3 + 2] = Math.cos(th) * R;
        }
        pos.set(base);
        baseHome = base.slice();
        target = base.slice();
        adj = Array.from({ length: N }, () => [] as number[]);
        G.L.forEach(([a, b]) => {
          adj[a].push(b);
          adj[b].push(a);
        });

        ng = new THREE.BufferGeometry();
        ng.setAttribute("position", new THREE.BufferAttribute(pos, 3));
        ng.setAttribute("aColor", new THREE.BufferAttribute(colArr, 3));
        ng.setAttribute("aSize", new THREE.BufferAttribute(sizeArr, 1));
        ng.setAttribute("aBright", new THREE.BufferAttribute(brightArr, 1));
        const nodeMat = new THREE.ShaderMaterial({
          uniforms: { uPix: { value: renderer.getPixelRatio() } },
          transparent: true,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
          vertexShader: `attribute vec3 aColor;attribute float aSize;attribute float aBright;
   varying vec3 vC;varying float vB;uniform float uPix;
   void main(){vC=aColor;vB=aBright;vec4 mv=modelViewMatrix*vec4(position,1.);
    gl_PointSize=(aSize*(2.1+aBright*3.2))*(360./-mv.z)*uPix;gl_Position=projectionMatrix*mv;}`,
          fragmentShader: `varying vec3 vC;varying float vB;
   void main(){float d=length(gl_PointCoord-.5);float core=smoothstep(.5,0.,d);float a=pow(core,1.6);
    // halo suave siempre presente (organismo luminoso en reposo) + núcleo brillante
    float halo=pow(core,3.2)*.5;
    vec3 col=mix(vC,vec3(1.),vB*.55+halo*.4);
    gl_FragColor=vec4(col*(.95+vB),a*(.82+vB*.7)+halo);}`,
        });
        points = new THREE.Points(ng, nodeMat);
        scene.add(points);

        IL = G.L.filter((e) => e[2]);
        linePos = new Float32Array(IL.length * 6);
        const lineCol = new Float32Array(IL.length * 6);
        for (let k = 0; k < IL.length; k++) {
          const c = palette[G.COL[IL[k][0]]];
          for (let s = 0; s < 2; s++) {
            lineCol[k * 6 + s * 3] = c.r;
            lineCol[k * 6 + s * 3 + 1] = c.g;
            lineCol[k * 6 + s * 3 + 2] = c.b;
          }
        }
        lg = new THREE.BufferGeometry();
        lg.setAttribute("position", new THREE.BufferAttribute(linePos, 3));
        lg.setAttribute("color", new THREE.BufferAttribute(lineCol, 3));
        lines = new THREE.LineSegments(
          lg,
          new THREE.LineBasicMaterial({
            vertexColors: true,
            transparent: true,
            opacity: 0.055,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
          }),
        );
        scene.add(lines);

        // render legend chips
        const legEl = mount.querySelector<HTMLDivElement>(".nebula-legend");
        if (legEl) {
          legEl.innerHTML = legend
            .map(
              (l) =>
                `<span class="nlrow"><i style="background:${l.c}"></i>${l.m}<b>${l.n}</b></span>`,
            )
            .join("");
        }

        started = true;
        // NO se dispara ningún "pensamiento" automático al cargar: Atlas
        // real está inactivo hasta que llega un evento real del bridge o el
        // operador actúa. Animar solo esta escena (mientras el sistema real
        // no hace nada) es exactamente la mentira que se señaló — el
        // organismo debe verse VIVO por su luz base, no por actividad falsa.
      })
      .catch(() => {
        const err = mount.querySelector<HTMLDivElement>(".nebula-legend");
        if (err) err.textContent = "grafo no disponible";
      });

    // ---- render loop ----
    let T = 0,
      lastT = performance.now();
    let frozen = false;
    // Hook de verificación: congela el lazo tras asentar un frame (permite
    // capturar bajo GL software; no afecta al uso real en GPU).
    (window as unknown as { __freezeNebula?: () => void }).__freezeNebula = () => {
      frozen = true;
    };
    const animate = () => {
      if (!frozen) raf = requestAnimationFrame(animate);
      const now = performance.now();
      const dt = Math.min((now - lastT) / 1000, 0.05);
      lastT = now;
      T += dt;
      if (started && ng && lg) {
        const amp = 2.4,
          fscale = 0.012,
          tsc = 0.05;
        for (let i = 0; i < N; i++) {
          const bx = target[i * 3],
            by = target[i * 3 + 1],
            bz = target[i * 3 + 2];
          base[i * 3] += (bx - base[i * 3]) * 0.05;
          base[i * 3 + 1] += (by - base[i * 3 + 1]) * 0.05;
          base[i * 3 + 2] += (bz - base[i * 3 + 2]) * 0.05;
          const cx = base[i * 3],
            cy = base[i * 3 + 1],
            cz = base[i * 3 + 2];
          const ox = sn3(cx * fscale + T * tsc, cy * fscale, cz * fscale);
          const oy = sn3(cx * fscale, cy * fscale + T * tsc, cz * fscale + 10);
          const oz = sn3(cx * fscale + 5, cy * fscale, cz * fscale + T * tsc);
          const em = 1 + brightArr[i] * 0.6;
          pos[i * 3] = cx + ox * amp * em;
          pos[i * 3 + 1] = cy + oy * amp * em;
          pos[i * 3 + 2] = cz + oz * amp * em;
          if (brightArr[i] > 0) brightArr[i] = Math.max(0, brightArr[i] - dt * 1.1);
        }
        ng.attributes.position.needsUpdate = true;
        ng.attributes.aBright.needsUpdate = true;
        for (let k = 0; k < IL.length; k++) {
          const a = IL[k][0],
            b = IL[k][1];
          linePos[k * 6] = pos[a * 3];
          linePos[k * 6 + 1] = pos[a * 3 + 1];
          linePos[k * 6 + 2] = pos[a * 3 + 2];
          linePos[k * 6 + 3] = pos[b * 3];
          linePos[k * 6 + 4] = pos[b * 3 + 1];
          linePos[k * 6 + 5] = pos[b * 3 + 2];
        }
        lg.attributes.position.needsUpdate = true;
        // token particles
        let pi = 0;
        for (let k = parts.length - 1; k >= 0; k--) {
          const p = parts[k];
          p.t += dt * 1.6;
          if (p.t >= 1) {
            parts.splice(k, 1);
            continue;
          }
          const a = p.a * 3,
            b = p.b * 3,
            tt = p.t;
          pp[pi * 3] = pos[a] + (pos[b] - pos[a]) * tt;
          pp[pi * 3 + 1] = pos[a + 1] + (pos[b + 1] - pos[a + 1]) * tt;
          pp[pi * 3 + 2] = pos[a + 2] + (pos[b + 2] - pos[a + 2]) * tt;
          pc[pi * 3] = p.c.r;
          pc[pi * 3 + 1] = p.c.g;
          pc[pi * 3 + 2] = p.c.b;
          pi++;
          if (pi >= PN) break;
        }
        pg.attributes.position.needsUpdate = true;
        pg.attributes.color.needsUpdate = true;
        pg.setDrawRange(0, pi);
        // query wave (memory)
        if (waveT >= 0) {
          waveT += dt * 0.5;
          const wr = waveT * 90;
          for (let i = 0; i < N; i++) {
            const d = Math.hypot(pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]);
            if (Math.abs(d - wr) < 8) brightArr[i] = Math.max(brightArr[i], 1);
          }
          if (waveT > 2.4) waveT = -1;
        }
      }
      // core pulse — exposición contenida (no blowout)
      const breath = 0.5 + 0.5 * Math.sin(T * 0.5);
      const cs = 22 + breath * 4 + (thinking ? 7 : 0);
      core.scale.set(cs, cs, 1);
      coreHalo.scale.set(cs * 2.4, cs * 2.4, 1);
      coreHaloMat.opacity = 0.22 + (thinking ? 0.14 : 0) + breath * 0.06;
      if (drone) drone.gain.value = soundOn ? 0.1 + (thinking ? 0.06 : 0) : 0;
      camR += (tR - camR) * 0.06;
      if (autorot && !reduce) camTh += dt * 0.03;
      updateCam();
      dust.rotation.y += dt * 0.006;
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(animate);
    void mode; // referenciado por setMode; sin lazo de "pensamiento" ficticio

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      ro.disconnect();
      removeEventListener("pointerup", onUp);
      removeEventListener("pointermove", onMove);
      removeEventListener("mousemove", onHover);
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("wheel", onWheel);
      renderer.dispose();
      scene.clear();
      if (AC) void AC.close();
      if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
    };
  }, [onPick, soundDefault]);

  return (
    <div ref={mountRef} className="nebula-mount">
      <div ref={tipRef} className="nebula-tip" />
      <div className="nebula-legend" />
    </div>
  );
});
