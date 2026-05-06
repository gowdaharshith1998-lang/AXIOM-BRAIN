import ForceGraph3D from "3d-force-graph";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { useEffect, useMemo, useRef } from "react";

import { envelopePosition } from "@/lib/brain-envelope";
import { RollingFpsCounter } from "@/lib/fps";
import { colorForType } from "@/lib/palette";
import { hasWebGPU, preferredRendererKind } from "@/lib/webgpu-detect";
import { BrainSocket } from "@/lib/websocket";
import { useBrainStore } from "@/state/brain.store";
import type { Edge, Entity } from "@/state/brain.store";

type GraphNode = {
  id: string;
  type: string;
  x?: number;
  y?: number;
  z?: number;
};

type GraphLink = {
  source: string;
  target: string;
};

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as T;
}

export function Brain() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<{ graphData: (d: { nodes: GraphNode[]; links: GraphLink[] }) => void } | null>(
    null,
  );
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const focusTargetRef = useRef<THREE.Vector3 | null>(null);

  const setFps = useBrainStore((s) => s.setFps);
  const applyEvent = useBrainStore((s) => s.applyEvent);
  const bootstrap = useBrainStore((s) => s.bootstrap);
  const select = useBrainStore((s) => s.select);
  const entities = useBrainStore((s) => s.entities);
  const edges = useBrainStore((s) => s.edges);

  const graphData = useMemo(() => {
    const nodes: GraphNode[] = Array.from(entities.values()).map((e) => {
      const [x, y, z] = envelopePosition(e.id);
      return { id: e.id, type: e.type, x, y, z };
    });
    const links: GraphLink[] = Array.from(edges.values()).map((ed) => ({
      source: ed.source_id,
      target: ed.target_id,
    }));
    return { nodes, links };
  }, [entities, edges]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [ents, eds] = await Promise.all([
        fetchJson<unknown[]>("http://127.0.0.1:8000/api/entities"),
        fetchJson<unknown[]>("http://127.0.0.1:8000/api/edges"),
      ]);
      if (cancelled) return;
      bootstrap(ents as Entity[], eds as Edge[]);
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [bootstrap]);

  useEffect(() => {
    const ws = new BrainSocket(`ws://${window.location.hostname}:8000/ws/brain`);
    const off = ws.on((e) => applyEvent(e));
    ws.start();
    return () => {
      off();
      ws.close();
    };
  }, [applyEvent]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const width = el.clientWidth;
    const height = el.clientHeight;

    const camera = new THREE.PerspectiveCamera(60, width / height, 1, 2000);
    camera.position.set(0, 40, 220);
    cameraRef.current = camera;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#0a0a14");

    const ambient = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambient);
    const dir = new THREE.DirectionalLight(0xffffff, 0.8);
    dir.position.set(1, 2, 3);
    scene.add(dir);

    const useGpu = hasWebGPU();

    type WebGpuRendererCtor = new (opts: { antialias: boolean; alpha: boolean }) => THREE.WebGLRenderer;
    const maybeThree = THREE as unknown as { WebGPURenderer?: WebGpuRendererCtor };
    const kind = preferredRendererKind({
      navigatorHasWebGpu: useGpu,
      threeHasWebGpuRenderer: typeof maybeThree.WebGPURenderer !== "undefined",
    });
    const renderer: THREE.WebGLRenderer =
      kind === "webgpu" && maybeThree.WebGPURenderer
        ? new maybeThree.WebGPURenderer({ antialias: true, alpha: false })
        : new THREE.WebGLRenderer({ antialias: true, alpha: false });

    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    el.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    composer.addPass(new UnrealBloomPass(new THREE.Vector2(width, height), 0.65, 0.6, 0.2));

    type ForceGraphFactory = (opts: { controlType: "orbit" }) => (el: HTMLElement) => unknown;
    const factory = ForceGraph3D as unknown as ForceGraphFactory;
    const fgUnknown = factory({ controlType: "orbit" })(document.createElement("div"));

    type ForceGraphApi = {
      graphData: (d: { nodes: GraphNode[]; links: GraphLink[] }) => ForceGraphApi;
      nodeRelSize: (n: number) => ForceGraphApi;
      nodeThreeObject: (fn: (n: unknown) => THREE.Object3D) => ForceGraphApi;
      linkColor: (fn: () => string) => ForceGraphApi;
      linkOpacity: (v: number) => ForceGraphApi;
      linkWidth: (v: number) => ForceGraphApi;
      cooldownTicks: (v: number) => ForceGraphApi;
      onNodeClick: (fn: (n: unknown) => void) => ForceGraphApi;
      _graph?: THREE.Object3D;
    };

    const fg = fgUnknown as ForceGraphApi;
    graphRef.current = { graphData: (d) => void fg.graphData(d) };

    const fgObj = fg
      .graphData({ nodes: [], links: [] })
      .nodeRelSize(4)
      .nodeThreeObject((n: unknown) => {
        const node = n as { type?: unknown };
        const color = new THREE.Color(colorForType(String(node.type)));
        const geom = new THREE.SphereGeometry(2.0, 12, 12);
        const mat = new THREE.MeshStandardMaterial({
          color,
          emissive: color,
          emissiveIntensity: 0.25,
        });
        return new THREE.Mesh(geom, mat);
      })
      .linkColor(() => "rgba(255,255,255,0.08)")
      .linkOpacity(0.35)
      .linkWidth(0.35)
      .cooldownTicks(0); // keep sim live but stable with only 100 nodes

    const forceObj: THREE.Object3D = fgObj._graph ?? new THREE.Group();
    scene.add(forceObj);

    // Click-to-focus (smooth lerp to selected node).
    fg.onNodeClick((n: unknown) => {
      const node = n as { id?: unknown; x?: unknown; y?: unknown; z?: unknown };
      if (typeof node.id === "string") select(node.id);
      if (
        typeof node.x === "number" &&
        typeof node.y === "number" &&
        typeof node.z === "number"
      ) {
        focusTargetRef.current = new THREE.Vector3(node.x, node.y, node.z);
      }
    });

    const fps = new RollingFpsCounter(60);
    let raf = 0;

    const tick = (t: number) => {
      const v = fps.tick(t);
      if (v) setFps(v);

      if (focusTargetRef.current) {
        const target = focusTargetRef.current;
        const desired = target.clone().add(new THREE.Vector3(0, 18, 55));
        camera.position.lerp(desired, 0.08);
        controls.target.lerp(target, 0.12);
        if (camera.position.distanceTo(desired) < 0.1) focusTargetRef.current = null;
      }

      controls.update();
      composer.render();
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);

    const onResize = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      composer.setSize(w, h);
    };
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      window.cancelAnimationFrame(raf);
      controls.dispose();
      composer.dispose();
      renderer.dispose();
      el.removeChild(renderer.domElement);
      scene.remove(forceObj);
    };
  }, [select, setFps]);

  useEffect(() => {
    // Update force-graph data when store changes.
    graphRef.current?.graphData(graphData);
  }, [graphData]);

  return <div ref={containerRef} className="absolute inset-0" aria-hidden="true" />;
}

