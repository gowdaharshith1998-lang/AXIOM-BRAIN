// frontend/src/components/Brain.tsx
//
// 3D visual brain. Owns its own Three.js scene + d3-force-3d simulation.
//
// Phase 4.1 fix (2026-05-06): The original Phase 4 implementation imported a
// turnkey force-graph renderer and tried to graft its private internals onto a
// separate Three.js scene. That unsupported field access failed silently and
// the scene rendered empty. Fix: own the simulation directly.
//
// Architecture:
//   - One scene, camera, renderer, EffectComposer (UnrealBloom + ACES).
//   - One d3-force-3d simulation with numDimensions=3.
//   - One Three.Mesh per entity (sphere with emissive material).
//   - One Three.LineSegments for ALL edges combined (single BufferGeometry).
//   - Initial positions seeded from envelopePosition(id) for stable visual.
//   - Simulation runs ~120 ticks then halts (alpha < 0.001).
//   - Render loop continues forever (orbit/zoom/click-focus stay live).

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
// d3-force-3d currently publishes no TypeScript declarations.
// @ts-expect-error missing declaration file for d3-force-3d
import { forceSimulation, forceManyBody, forceLink, forceCenter } from "d3-force-3d";
import { useEffect, useMemo, useRef } from "react";

import { envelopePosition } from "@/lib/brain-envelope";
import { RollingFpsCounter } from "@/lib/fps";
import { colorForType } from "@/lib/palette";
import { hasWebGPU, preferredRendererKind } from "@/lib/webgpu-detect";
import { BrainSocket } from "@/lib/websocket";
import { useBrainStore } from "@/state/brain.store";
import type { Edge, Entity } from "@/state/brain.store";

// d3-force-3d mutates these fields on every simulation tick.
type SimNode = {
  id: string;
  type: string;
  index?: number;
  x?: number;
  y?: number;
  z?: number;
  vx?: number;
  vy?: number;
  vz?: number;
};

type SimLink = {
  source: string | SimNode;
  target: string | SimNode;
};

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as T;
}

const NODE_RADIUS = 2.0;
const SIM_TICKS_BEFORE_REST = 120;
const SIM_REST_ALPHA = 0.001;

export function Brain() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const focusTargetRef = useRef<THREE.Vector3 | null>(null);

  const setFps = useBrainStore((s) => s.setFps);
  const applyEvent = useBrainStore((s) => s.applyEvent);
  const bootstrap = useBrainStore((s) => s.bootstrap);
  const select = useBrainStore((s) => s.select);
  const entities = useBrainStore((s) => s.entities);
  const edges = useBrainStore((s) => s.edges);

  // -- Bootstrap data from REST --
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [ents, eds] = await Promise.all([
          fetchJson<unknown[]>("http://127.0.0.1:8000/api/entities"),
          fetchJson<unknown[]>("http://127.0.0.1:8000/api/edges"),
        ]);
        if (cancelled) return;
        bootstrap(ents as Entity[], eds as Edge[]);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("[Brain] bootstrap failed:", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [bootstrap]);

  // -- Live event stream via WebSocket --
  useEffect(() => {
    const url = `ws://${window.location.hostname}:8000/ws/brain`;
    const ws = new BrainSocket(url);
    const off = ws.on((e) => applyEvent(e));
    ws.start();
    return () => {
      off();
      ws.close();
    };
  }, [applyEvent]);

  // -- Memoize sim data (avoid re-running effect on every render) --
  const simData = useMemo(() => {
    const nodes: SimNode[] = Array.from(entities.values()).map((e) => {
      const [x, y, z] = envelopePosition(e.id);
      return { id: e.id, type: e.type, x, y, z };
    });
    // Edges may reference entities not yet in the store; filter to safe links.
    const nodeIds = new Set(nodes.map((n) => n.id));
    const links: SimLink[] = Array.from(edges.values())
      .filter((ed) => nodeIds.has(ed.source_id) && nodeIds.has(ed.target_id))
      .map((ed) => ({ source: ed.source_id, target: ed.target_id }));
    return { nodes, links };
  }, [entities, edges]);

  // -- Three.js scene + d3-force-3d simulation lifecycle --
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    if (simData.nodes.length === 0) return; // wait for bootstrap

    const width = el.clientWidth;
    const height = el.clientHeight;

    // ----- Scene + camera -----
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#0a0a14");

    const camera = new THREE.PerspectiveCamera(60, width / height, 1, 2000);
    camera.position.set(0, 40, 220);

    // ----- Lights (essential: MeshStandardMaterial is black without them) -----
    const ambient = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambient);
    const dir = new THREE.DirectionalLight(0xffffff, 0.8);
    dir.position.set(1, 2, 3);
    scene.add(dir);

    // ----- Renderer (WebGPU primary, WebGL fallback) -----
    const useGpu = hasWebGPU();
    type WebGpuRendererCtor = new (opts: { antialias: boolean; alpha: boolean }) => THREE.WebGLRenderer;
    const maybeThree = THREE as unknown as { WebGPURenderer?: WebGpuRendererCtor };
    const kind = preferredRendererKind({
      navigatorHasWebGpu: useGpu,
      threeHasWebGpuRenderer: typeof maybeThree.WebGPURenderer !== "undefined",
    });

    let renderer: THREE.WebGLRenderer;
    try {
      renderer =
        kind === "webgpu" && maybeThree.WebGPURenderer
          ? new maybeThree.WebGPURenderer({ antialias: true, alpha: false })
          : new THREE.WebGLRenderer({ antialias: true, alpha: false });
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("[Brain] WebGPU init failed, falling back to WebGL:", err);
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    }

    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    el.appendChild(renderer.domElement);

    // ----- Orbit controls -----
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

    // ----- Post-processing: UnrealBloom + ACES via composer -----
    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    composer.addPass(new UnrealBloomPass(new THREE.Vector2(width, height), 0.65, 0.6, 0.2));

    // ----- Build node meshes -----
    const nodeGroup = new THREE.Group();
    scene.add(nodeGroup);

    const sphereGeom = new THREE.SphereGeometry(NODE_RADIUS, 14, 14);
    const meshById = new Map<string, THREE.Mesh>();

    for (const n of simData.nodes) {
      const color = new THREE.Color(colorForType(n.type));
      const mat = new THREE.MeshStandardMaterial({
        color,
        emissive: color,
        emissiveIntensity: 0.6,
        roughness: 0.4,
        metalness: 0.1,
      });
      const mesh = new THREE.Mesh(sphereGeom, mat);
      mesh.position.set(n.x ?? 0, n.y ?? 0, n.z ?? 0);
      mesh.userData = { id: n.id, type: n.type };
      nodeGroup.add(mesh);
      meshById.set(n.id, mesh);
    }

    // ----- Build edge geometry (one LineSegments for all edges) -----
    const edgeCount = simData.links.length;
    const edgePositions = new Float32Array(edgeCount * 2 * 3);
    const edgeGeom = new THREE.BufferGeometry();
    edgeGeom.setAttribute("position", new THREE.BufferAttribute(edgePositions, 3));
    const edgeMat = new THREE.LineBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.18,
    });
    const edgeLines = new THREE.LineSegments(edgeGeom, edgeMat);
    scene.add(edgeLines);

    // ----- d3-force-3d simulation -----
    const sim = forceSimulation(simData.nodes, 3)
      .force("charge", forceManyBody().strength(-30))
      .force(
        "link",
        forceLink(simData.links)
          .id((n: SimNode) => n.id)
          .distance(20)
          .strength(0.4),
      )
      .force("center", forceCenter())
      .alphaDecay(0.05)
      .stop();

    let simTicks = 0;

    const stepSim = () => {
      if (simTicks >= SIM_TICKS_BEFORE_REST) return;
      if (sim.alpha() < SIM_REST_ALPHA) return;
      sim.tick();
      simTicks++;
    };

    // ----- Per-frame: copy sim positions to meshes, refresh edge geometry -----
    const syncPositions = () => {
      for (const n of simData.nodes) {
        const mesh = meshById.get(n.id);
        if (!mesh) continue;
        mesh.position.set(n.x ?? 0, n.y ?? 0, n.z ?? 0);
      }

      const posAttr = edgeGeom.attributes.position as THREE.BufferAttribute;
      const arr = posAttr.array as Float32Array;
      let idx = 0;
      for (const link of simData.links) {
        const src = typeof link.source === "object" ? link.source : undefined;
        const tgt = typeof link.target === "object" ? link.target : undefined;
        if (!src || !tgt) {
          idx += 6;
          continue;
        }
        arr[idx++] = src.x ?? 0;
        arr[idx++] = src.y ?? 0;
        arr[idx++] = src.z ?? 0;
        arr[idx++] = tgt.x ?? 0;
        arr[idx++] = tgt.y ?? 0;
        arr[idx++] = tgt.z ?? 0;
      }
      posAttr.needsUpdate = true;
    };

    // ----- Click-to-focus via raycaster -----
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const onPointerDown = (ev: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hits = raycaster.intersectObjects(nodeGroup.children, false);
      if (hits.length === 0) return;
      const mesh = hits[0].object as THREE.Mesh;
      const id = (mesh.userData as { id?: string }).id;
      if (typeof id === "string") select(id);
      focusTargetRef.current = mesh.position.clone();
    };
    renderer.domElement.addEventListener("pointerdown", onPointerDown);

    // ----- Render loop -----
    const fps = new RollingFpsCounter(60);
    let raf = 0;

    const tick = (t: number) => {
      stepSim();
      syncPositions();

      const v = fps.tick(t);
      if (v) setFps(v);

      if (focusTargetRef.current) {
        const target = focusTargetRef.current;
        const desired = target.clone().add(new THREE.Vector3(0, 18, 55));
        camera.position.lerp(desired, 0.08);
        controls.target.lerp(target, 0.12);
        if (camera.position.distanceTo(desired) < 0.1) {
          focusTargetRef.current = null;
        }
      }

      controls.update();
      composer.render();
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);

    // ----- Resize -----
    const onResize = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      composer.setSize(w, h);
    };
    window.addEventListener("resize", onResize);

    // ----- Cleanup -----
    return () => {
      window.removeEventListener("resize", onResize);
      window.cancelAnimationFrame(raf);
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      sim.stop();
      controls.dispose();
      composer.dispose();
      renderer.dispose();
      sphereGeom.dispose();
      edgeGeom.dispose();
      edgeMat.dispose();
      meshById.forEach((m) => {
        (m.material as THREE.Material).dispose();
      });
      if (renderer.domElement.parentNode === el) {
        el.removeChild(renderer.domElement);
      }
    };
  }, [simData, select, setFps]);

  return <div ref={containerRef} className="absolute inset-0" aria-hidden="true" />;
}

