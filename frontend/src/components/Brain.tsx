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

import { AutoOrbitController } from "@/lib/auto-orbit";
import { envelopePosition } from "@/lib/brain-envelope";
import { colorForRelationship } from "@/lib/edge-tint";
import { RollingFpsCounter } from "@/lib/fps";
import { FpsGuard } from "@/lib/fps-guard";
import { colorForType } from "@/lib/palette";
import { ParticleEffectSystem } from "@/lib/particles/agent-effects";
import { EdgeShimmer, createEdgeShimmerMaterial } from "@/lib/particles/edge-shimmer";
import { IdlePulseRunner } from "@/lib/particles/idle-pulse-runner";
import { createNebulaBackground } from "@/lib/particles/nebula-bg";
import { OrbitalHalo } from "@/lib/particles/orbital-halo";
import { spawnEdgeTrace, spawnEntityArrival } from "@/lib/particles/reactive-spawn";
import { hasWebGPU, preferredRendererKind } from "@/lib/webgpu-detect";
import { BrainSocket } from "@/lib/websocket";
import type { BrainEvent } from "@/lib/websocket";
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
  id: string;
  relationship: string;
};

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as T;
}

const NODE_RADIUS = 2.0;
const SIM_TICKS_BEFORE_REST = 120;
const SIM_REST_ALPHA = 0.001;

function payloadString(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === "string" ? value : null;
}

export function Brain() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const focusTargetRef = useRef<THREE.Vector3 | null>(null);
  const liveEventsRef = useRef<BrainEvent[]>([]);

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
    const off = ws.on((e) => {
      liveEventsRef.current.push(e);
      applyEvent(e);
    });
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
      .map((ed) => ({ id: ed.id, source: ed.source_id, target: ed.target_id, relationship: ed.relationship }));
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
    const nebula = createNebulaBackground();
    scene.add(nebula.mesh);

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
    const ringGeom = new THREE.TorusGeometry(NODE_RADIUS * 2.0, 0.035, 6, 40);
    const meshById = new Map<string, THREE.Mesh>();
    const ringById = new Map<string, THREE.Mesh<THREE.TorusGeometry, THREE.MeshBasicMaterial>>();
    const neighborIds = new Map<string, Set<string>>();

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

      const ringMat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });
      const ring = new THREE.Mesh(ringGeom, ringMat);
      ring.visible = false;
      nodeGroup.add(ring);
      ringById.set(n.id, ring);
      neighborIds.set(n.id, new Set());
    }

    for (const link of simData.links) {
      const sourceId = typeof link.source === "string" ? link.source : link.source.id;
      const targetId = typeof link.target === "string" ? link.target : link.target.id;
      neighborIds.get(sourceId)?.add(targetId);
      neighborIds.get(targetId)?.add(sourceId);
    }

    // ----- Build edge geometry (one LineSegments for all edges) -----
    const edgeCount = simData.links.length;
    const edgePositions = new Float32Array(edgeCount * 2 * 3);
    const edgeColors = new Float32Array(edgeCount * 2 * 3);
    const edgeGeom = new THREE.BufferGeometry();
    edgeGeom.setAttribute("position", new THREE.BufferAttribute(edgePositions, 3));
    edgeGeom.setAttribute("color", new THREE.BufferAttribute(edgeColors, 3));
    const edgeMat = createEdgeShimmerMaterial();
    const edgeLines = new THREE.LineSegments(edgeGeom, edgeMat);
    scene.add(edgeLines);
    const edgeShimmer = new EdgeShimmer(
      simData.links.map((link) => link.id),
      edgeGeom,
    );

    const particleSystem = new ParticleEffectSystem();
    scene.add(particleSystem.points);

    let orbitalHalo: OrbitalHalo | null = null;

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
        const ring = ringById.get(n.id);
        if (ring) ring.position.copy(mesh.position);
      }

      const posAttr = edgeGeom.attributes.position as THREE.BufferAttribute;
      const arr = posAttr.array as Float32Array;
      const colorAttr = edgeGeom.attributes.color as THREE.BufferAttribute;
      const colorArr = colorAttr.array as Float32Array;
      let idx = 0;
      let colorIdx = 0;
      for (const link of simData.links) {
        const src = typeof link.source === "object" ? link.source : undefined;
        const tgt = typeof link.target === "object" ? link.target : undefined;
        if (!src || !tgt) {
          idx += 6;
          colorIdx += 6;
          continue;
        }
        arr[idx++] = src.x ?? 0;
        arr[idx++] = src.y ?? 0;
        arr[idx++] = src.z ?? 0;
        arr[idx++] = tgt.x ?? 0;
        arr[idx++] = tgt.y ?? 0;
        arr[idx++] = tgt.z ?? 0;

        const edgeColor = new THREE.Color(colorForRelationship(link.relationship));
        for (let i = 0; i < 2; i++) {
          colorArr[colorIdx++] = edgeColor.r;
          colorArr[colorIdx++] = edgeColor.g;
          colorArr[colorIdx++] = edgeColor.b;
        }
      }
      posAttr.needsUpdate = true;
      colorAttr.needsUpdate = true;
    };

    // ----- Interaction: hover rings, click focus, auto-orbit wake -----
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const hoveredIdRef = { current: null as string | null };
    const flashByNode = new Map<string, number>();
    const flashByEdge = new Map<string, number>();
    const autoOrbit = new AutoOrbitController();
    autoOrbit.notifyInteraction(0);

    const setPointer = (ev: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
    };

    const hitNode = (): THREE.Mesh | null => {
      raycaster.setFromCamera(pointer, camera);
      const hits = raycaster.intersectObjects(Array.from(meshById.values()), false);
      return hits.length > 0 ? (hits[0].object as THREE.Mesh) : null;
    };

    const onPointerMove = (ev: PointerEvent) => {
      setPointer(ev);
      const mesh = hitNode();
      hoveredIdRef.current = mesh ? ((mesh.userData as { id?: string }).id ?? null) : null;
    };

    const onPointerDown = (ev: PointerEvent) => {
      autoOrbit.notifyInteraction(ev.timeStamp);
      setPointer(ev);
      const mesh = hitNode();
      if (!mesh) return;
      const id = (mesh.userData as { id?: string }).id;
      if (typeof id !== "string") return;
      select(id);
      focusTargetRef.current = mesh.position.clone();
      flashByNode.set(id, ev.timeStamp + 450);

      const meshMaterial = mesh.material;
      const color =
        meshMaterial instanceof THREE.MeshStandardMaterial ? meshMaterial.color.clone() : new THREE.Color("#FFFFFF");
      if (orbitalHalo) {
        scene.remove(orbitalHalo.points);
        orbitalHalo.dispose();
      }
      orbitalHalo = new OrbitalHalo(color);
      orbitalHalo.setTarget(mesh.position, NODE_RADIUS * 3.2, color);
      scene.add(orbitalHalo.points);
    };
    const notifyOrbitInteraction = (ev: Event) => autoOrbit.notifyInteraction(ev.timeStamp);
    renderer.domElement.addEventListener("pointermove", onPointerMove);
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("wheel", notifyOrbitInteraction, { passive: true });
    renderer.domElement.addEventListener("touchstart", notifyOrbitInteraction, { passive: true });

    // ----- Render loop -----
    const fps = new RollingFpsCounter(60);
    const fpsGuard = new FpsGuard();
    const pulseRunner = new IdlePulseRunner();
    let raf = 0;
    let lastFrameMs = 0;

    const processLiveEvents = (nowMs: number) => {
      const deferred: BrainEvent[] = [];
      for (const event of liveEventsRef.current) {
        if (event.type === "entity_added" && event.persisted_id) {
          const mesh = meshById.get(event.persisted_id);
          if (!mesh) {
            deferred.push(event);
            continue;
          }
          const material = mesh.material;
          const color =
            material instanceof THREE.MeshStandardMaterial ? material.color.clone() : new THREE.Color("#FFFFFF");
          spawnEntityArrival(particleSystem, mesh.position, color);
          particleSystem.ingestStream(mesh.position, `#${color.getHexString().toUpperCase()}`);
          flashByNode.set(event.persisted_id, nowMs + 600);
          continue;
        }

        if (event.type === "edge_added" && event.persisted_id) {
          const sourceId = payloadString(event.payload, "source_id");
          const targetId = payloadString(event.payload, "target_id");
          const relationship = payloadString(event.payload, "relationship") ?? "";
          const src = sourceId ? meshById.get(sourceId) : undefined;
          const tgt = targetId ? meshById.get(targetId) : undefined;
          if (!src || !tgt) {
            deferred.push(event);
            continue;
          }
          spawnEdgeTrace(particleSystem, src.position, tgt.position, colorForRelationship(relationship));
          flashByEdge.set(event.persisted_id, nowMs + 600);
          continue;
        }

        if (event.type === "entity_modified") {
          const id = event.persisted_id ?? event.source_id;
          const mesh = meshById.get(id);
          if (!mesh) continue;
          const material = mesh.material;
          const color =
            material instanceof THREE.MeshStandardMaterial ? `#${material.color.getHexString().toUpperCase()}` : "#FFFFFF";
          particleSystem.signingBurst(mesh.position, color);
          flashByNode.set(id, nowMs + 500);
        }
      }
      liveEventsRef.current = deferred.slice(-20);
    };

    const updateHoverAndRings = () => {
      const hoveredId = hoveredIdRef.current;
      const activeNeighbors = hoveredId ? neighborIds.get(hoveredId) : null;
      for (const [id, mesh] of meshById) {
        const targetScale = id === hoveredId ? 1.2 : 1;
        mesh.scale.lerp(new THREE.Vector3(targetScale, targetScale, targetScale), 0.15);

        const ring = ringById.get(id);
        if (!ring) continue;
        const isHover = id === hoveredId;
        const isNeighbor = activeNeighbors?.has(id) ?? false;
        const targetOpacity = isHover ? 0.45 : isNeighbor ? 0.18 : 0;
        ring.visible = targetOpacity > 0.01 || ring.material.opacity > 0.01;
        ring.material.opacity += (targetOpacity - ring.material.opacity) * 0.18;
        ring.lookAt(camera.position);
      }
    };

    const updateFlashes = (nowMs: number) => {
      for (const [id, until] of flashByNode) {
        const mesh = meshById.get(id);
        if (!mesh || nowMs > until) {
          flashByNode.delete(id);
          continue;
        }
        const material = mesh.material;
        if (material instanceof THREE.MeshStandardMaterial) {
          material.emissiveIntensity += ((until - nowMs) / 600) * 1.2;
        }
      }

      const alphaAttr = edgeGeom.getAttribute("edgeAlpha");
      if (!(alphaAttr instanceof THREE.BufferAttribute)) return;
      const alphaArr = alphaAttr.array as Float32Array;
      simData.links.forEach((link, i) => {
        const until = flashByEdge.get(link.id);
        if (until === undefined) return;
        if (nowMs > until) {
          flashByEdge.delete(link.id);
          return;
        }
        const alpha = 0.45 * ((until - nowMs) / 600);
        alphaArr[i * 2] = Math.max(alphaArr[i * 2], alpha);
        alphaArr[i * 2 + 1] = Math.max(alphaArr[i * 2 + 1], alpha);
      });
      alphaAttr.needsUpdate = true;
    };

    const tick = (t: number) => {
      const dtMs = lastFrameMs === 0 ? 16.7 : t - lastFrameMs;
      lastFrameMs = t;
      stepSim();
      syncPositions();
      processLiveEvents(t);
      nebula.update(t);
      pulseRunner.update(meshById, t);
      edgeShimmer.update(t);
      updateHoverAndRings();
      updateFlashes(t);
      particleSystem.setParticleMultiplier(fpsGuard.particleMultiplier());
      particleSystem.update(t);
      orbitalHalo?.update(t);

      const v = fps.tick(t);
      if (v) {
        setFps(v);
        fpsGuard.sample(v, t);
      }

      if (focusTargetRef.current) {
        const target = focusTargetRef.current;
        const desired = target.clone().add(new THREE.Vector3(0, 18, 55));
        camera.position.lerp(desired, 0.08);
        controls.target.lerp(target, 0.12);
        if (camera.position.distanceTo(desired) < 0.1) {
          focusTargetRef.current = null;
        }
      }

      autoOrbit.applyToCamera(camera, t, dtMs);
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
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("wheel", notifyOrbitInteraction);
      renderer.domElement.removeEventListener("touchstart", notifyOrbitInteraction);
      sim.stop();
      controls.dispose();
      composer.dispose();
      nebula.dispose();
      particleSystem.dispose();
      orbitalHalo?.dispose();
      renderer.dispose();
      sphereGeom.dispose();
      ringGeom.dispose();
      edgeGeom.dispose();
      edgeMat.dispose();
      meshById.forEach((m) => {
        (m.material as THREE.Material).dispose();
      });
      ringById.forEach((r) => {
        r.material.dispose();
      });
      if (renderer.domElement.parentNode === el) {
        el.removeChild(renderer.domElement);
      }
    };
  }, [simData, select, setFps]);

  return <div ref={containerRef} className="absolute inset-0" aria-hidden="true" />;
}

