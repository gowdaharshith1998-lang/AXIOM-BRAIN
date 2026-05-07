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
import { CSS2DObject, CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
// d3-force-3d currently publishes no TypeScript declarations.
// @ts-expect-error missing declaration file for d3-force-3d
import { forceSimulation, forceManyBody, forceLink, forceCenter, forceRadial } from "d3-force-3d";
import { useEffect, useRef, useState } from "react";

import { createClusterAuras, setAurasVisible, updateClusterAuras } from "@/components/ClusterAura";
import { arrivalColorForCluster } from "@/components/ArrivalEffect";
import { AutoOrbitController } from "@/lib/auto-orbit";
import { envelopePosition } from "@/lib/brain-envelope";
import { easeInOutCubic, RESET_CAMERA_MS, shouldResetCameraFromKey } from "@/lib/camera-reset";
import { flyToEntity } from "@/lib/camera-flyto";
import { resolveLabelCollisions, type LabelBox } from "@/lib/cluster-label-collision";
import {
  CLUSTER_CENTROIDS,
  CLUSTER_COLORS,
  CLUSTER_GRAVITY_DEFAULT,
  CLUSTER_IDS,
  CLUSTER_LABELS,
  CLUSTER_LABEL_HIDE_DISTANCE,
  CLUSTER_LABEL_SHOW_DISTANCE,
  CROSS_CLUSTER_EDGE_OPACITY,
  CROSS_CLUSTER_EDGE_WIDTH,
  SAME_CLUSTER_EDGE_OPACITY,
  SAME_CLUSTER_EDGE_WIDTH,
  clusterGravityForce,
  isClusterId,
  type ClusterId,
} from "@/lib/cluster-layout";
import { colorForRelationship } from "@/lib/edge-tint";
import { edgeDrawEndpoint, isEdgeDrawActive } from "@/lib/edge-animation";
import { edgeAlphaForLod, edgeOpacityForClusters } from "@/lib/edge-style";
import { RollingFpsCounter } from "@/lib/fps";
import { FpsGuard, type FpsGuardState } from "@/lib/fps-guard";
import {
  BLOOM_FULL_STRENGTH,
  bloomStrengthForDistance,
  createNodeSpriteMaterial,
  nodeLodMode,
  shouldRenderEdge,
} from "@/lib/lod";
import {
  displayLabelFor,
  LABEL_SHOW_DISTANCE_MAX,
  LABEL_FPS_HIDE_THRESHOLD,
  LABEL_FPS_RECOVER_THRESHOLD,
  LABEL_OVERVIEW_CAP,
  shouldShowLabel,
} from "@/lib/labels";
import { colorForType } from "@/lib/palette";
import { ParticleEffectSystem } from "@/lib/particles/agent-effects";
import { createEdgeShimmerMaterial, phaseOffsetFromEdgeKey, updateEdgeShimmer } from "@/lib/particles/edge-shimmer";
import { IdlePulseRunner } from "@/lib/particles/idle-pulse-runner";
import { createNebulaBackground } from "@/lib/particles/nebula-bg";
import { OrbitalHalo } from "@/lib/particles/orbital-halo";
import { spawnEdgeTrace, spawnEntityArrival } from "@/lib/particles/reactive-spawn";
import {
  createSynapticFlow,
  disposeSynapticFlow,
  updateSynapticFlow,
  type SynapticFlowEdge,
} from "@/lib/particles/synaptic-flow";
import { hasWebGPU, preferredRendererKind } from "@/lib/webgpu-detect";
import { BrainSocket } from "@/lib/websocket";
import type { BrainEvent } from "@/lib/websocket";
import { useBrainStore } from "@/state/brain.store";
import type { Edge, Entity } from "@/state/brain.store";

// d3-force-3d mutates these fields on every simulation tick.
type SimNode = {
  id: string;
  type: string;
  lod?: LodLevel;
  index?: number;
  x?: number;
  y?: number;
  z?: number;
  vx?: number;
  vy?: number;
  vz?: number;
  cluster_id?: string | null;
};

type SimLink = {
  source: string | SimNode;
  target: string | SimNode;
  id: string;
  relationship: string;
};

type LodLevel = "near" | "far";

type TuneableForce = {
  strength?: (value: number) => TuneableForce;
  distance?: (value: number) => TuneableForce;
};

type TuneableSimulation = {
  force: (name: string) => TuneableForce | undefined;
};

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as T;
}

const NODE_RADIUS = 2.0;
const SIM_TICKS_BEFORE_REST = 120;
const SIM_REST_ALPHA = 0.001;
const INITIAL_CAMERA_POSITION = new THREE.Vector3(0, 40, 220);
const CAMERA_ANIMATION_MS = RESET_CAMERA_MS;
const AUTO_FIT_ENTITY_STEP = 500;
const USER_IDLE_AUTO_FIT_MS = 10_000;
const FAR_LOD_DISTANCE = 180;
const FAR_NODE_SCALE = 0.35;
const FAR_EDGE_ALPHA = 0.12;
const LABEL_OVERVIEW_ENTITY_LIMIT = 3000;
const BASE_NODE_EMISSIVE = 0.2;
const FAR_NODE_EMISSIVE = 0.05;
const SELECTED_NODE_EMISSIVE = 0.4;
const NEIGHBOR_NODE_EMISSIVE = 0.3;
const DIMMED_NODE_EMISSIVE = BASE_NODE_EMISSIVE * 0.5;
const IDLE_PULSE_IMPORTANCE_THRESHOLD = 0.4;
const SYNAPTIC_FLOW_IMPORTANCE_THRESHOLD = 0.3;

function tuneForcesByCount(sim: TuneableSimulation, entityCount: number): void {
  const c = Math.max(entityCount, 1);
  // Keep the whole graph in one visual envelope as density grows.
  const centerStrength = Math.min(0.05 + Math.log10(c) * 0.02, 0.15);
  const chargeStrength = -30 * Math.pow(100 / Math.max(c, 100), 0.5);
  const linkDistance = Math.max(20, 60 - Math.log10(c) * 8);
  const linkStrength = Math.min(0.4 + Math.log10(c) * 0.05, 0.7);

  sim.force("center")?.strength?.(centerStrength);
  sim.force("charge")?.strength?.(chargeStrength);
  sim.force("link")?.distance?.(linkDistance).strength?.(linkStrength);
}

function nextEntityThreshold(entityCount: number): number {
  return Math.floor(entityCount / AUTO_FIT_ENTITY_STEP) * AUTO_FIT_ENTITY_STEP;
}

function compositeImportance(entity: Entity | undefined): number {
  if (!entity) return 0;
  const top = entity.composite_importance;
  if (typeof top === "number" && Number.isFinite(top)) return top;
  const nested = entity.data?.composite_importance;
  return typeof nested === "number" && Number.isFinite(nested) ? nested : 0;
}

function clusterIdFor(entity: Entity | undefined): ClusterId | null {
  if (!entity) return null;
  const direct = entity.cluster_id;
  if (isClusterId(direct)) return direct;
  return null;
}

const NODE_RADIUS_IMPORTANCE_BOOST = 1.5;
const NODE_EMISSIVE_IMPORTANCE_BOOST = 0.15;
const NODE_DRIFT_DURATION_MS = 800;

function labelImportance(entity: Entity | undefined, connectionCount = 0): number {
  return compositeImportance(entity) || connectionCount / 1000;
}

export function Brain() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const focusTargetRef = useRef<THREE.Vector3 | null>(null);
  const liveEventsRef = useRef<BrainEvent[]>([]);
  const [sceneReady, setSceneReady] = useState(false);

  const setFps = useBrainStore((s) => s.setFps);
  const setConnectionStatus = useBrainStore((s) => s.setConnectionStatus);
  const applyEvent = useBrainStore((s) => s.applyEvent);
  const bootstrap = useBrainStore((s) => s.bootstrap);
  const select = useBrainStore((s) => s.select);

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
        setSceneReady(true);
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
    setConnectionStatus("syncing");
    const off = ws.on((e) => {
      liveEventsRef.current.push(e);
      applyEvent(e);
    });
    const offStatus = ws.onStatus(setConnectionStatus);
    ws.start();
    return () => {
      off();
      offStatus();
      ws.close();
    };
  }, [applyEvent, setConnectionStatus]);

  // -- Three.js scene + d3-force-3d simulation lifecycle --
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    if (!sceneReady) return; // wait for REST bootstrap so initial edges are present

    const { entities, edges } = useBrainStore.getState();
    const simData = (() => {
      const nodes: SimNode[] = Array.from(entities.values()).map((e) => {
        const [x, y, z] = envelopePosition(e.id);
        const cluster = clusterIdFor(e);
        return { id: e.id, type: e.type, x, y, z, cluster_id: cluster };
      });
      // Edges may reference entities not yet in the store; filter to safe links.
      const nodeIds = new Set(nodes.map((n) => n.id));
      const links: SimLink[] = Array.from(edges.values())
        .filter((ed) => nodeIds.has(ed.source_id) && nodeIds.has(ed.target_id))
        .map((ed) => ({ id: ed.id, source: ed.source_id, target: ed.target_id, relationship: ed.relationship }));
      return { nodes, links };
    })();

    const width = el.clientWidth;
    const height = el.clientHeight;

    // ----- Scene + camera -----
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#0a0a14");
    const nebula = createNebulaBackground();
    scene.add(nebula.mesh);
    const clusterAuras = createClusterAuras();
    for (const aura of clusterAuras) scene.add(aura);

    const camera = new THREE.PerspectiveCamera(60, width / height, 1, 4000);
    camera.position.copy(INITIAL_CAMERA_POSITION);

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
    renderer.toneMappingExposure = 0.85;
    el.appendChild(renderer.domElement);

    // ----- Orbit controls -----
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

    // ----- Post-processing: UnrealBloom + ACES via composer -----
    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloomPass = new UnrealBloomPass(new THREE.Vector2(width, height), BLOOM_FULL_STRENGTH, 0.35, 0.92);
    composer.addPass(bloomPass);

    // ----- DOM label overlay (non-interactive; OrbitControls keep pointer ownership) -----
    const labelRenderer = new CSS2DRenderer();
    labelRenderer.setSize(width, height);
    labelRenderer.domElement.classList.add("axiom-labels");
    labelRenderer.domElement.style.position = "absolute";
    labelRenderer.domElement.style.top = "0";
    labelRenderer.domElement.style.left = "0";
    labelRenderer.domElement.style.pointerEvents = "none";
    labelRenderer.domElement.style.color = "rgba(255, 255, 255, 0.7)";
    labelRenderer.domElement.style.fontSize = "11px";
    labelRenderer.domElement.style.fontFamily = "ui-sans-serif, system-ui, sans-serif";
    labelRenderer.domElement.style.fontWeight = "500";
    labelRenderer.domElement.style.textShadow = "0 0 2px rgba(0,0,0,0.9), 0 1px 2px rgba(0,0,0,0.7)";
    labelRenderer.domElement.style.userSelect = "none";
    el.appendChild(labelRenderer.domElement);

    // ----- Cluster centroid labels (visible at overview zoom) -----
    const clusterLabelGroup = new THREE.Group();
    scene.add(clusterLabelGroup);
    const clusterLabelByCluster = new Map<ClusterId, HTMLDivElement>();
    const clusterLabelObjectByCluster = new Map<ClusterId, CSS2DObject>();
    const clusterCountByCluster = new Map<ClusterId, number>();
    for (const cluster of CLUSTER_IDS) {
      const centroid = CLUSTER_CENTROIDS[cluster];
      const labelDiv = document.createElement("div");
      labelDiv.className = "axiom-cluster-label";
      labelDiv.dataset.cluster = cluster;
      labelDiv.style.color = CLUSTER_COLORS[cluster];
      labelDiv.style.fontSize = "14px";
      labelDiv.style.fontWeight = "600";
      labelDiv.style.letterSpacing = "0.04em";
      labelDiv.style.textTransform = "uppercase";
      labelDiv.style.opacity = "0";
      labelDiv.style.transition = "opacity 350ms ease-out";
      labelDiv.style.pointerEvents = "none";
      labelDiv.style.userSelect = "none";
      labelDiv.style.transform = "translate(-50%, -50%)";
      labelDiv.style.whiteSpace = "nowrap";
      labelDiv.style.textShadow = "0 0 6px rgba(0,0,0,0.95), 0 1px 2px rgba(0,0,0,0.85)";
      labelDiv.textContent = `${CLUSTER_LABELS[cluster]} · 0`;
      const labelObj = new CSS2DObject(labelDiv);
      labelObj.position.copy(centroid);
      clusterLabelGroup.add(labelObj);
      clusterLabelByCluster.set(cluster, labelDiv);
      clusterLabelObjectByCluster.set(cluster, labelObj);
      clusterCountByCluster.set(cluster, 0);
    }

    const refreshClusterCounts = () => {
      const tally = new Map<ClusterId, number>();
      for (const cluster of CLUSTER_IDS) tally.set(cluster, 0);
      for (const node of simData.nodes) {
        if (isClusterId(node.cluster_id)) {
          tally.set(node.cluster_id, (tally.get(node.cluster_id) ?? 0) + 1);
        }
      }
      for (const cluster of CLUSTER_IDS) {
        const count = tally.get(cluster) ?? 0;
        if (clusterCountByCluster.get(cluster) === count) continue;
        clusterCountByCluster.set(cluster, count);
        const div = clusterLabelByCluster.get(cluster);
        if (div) div.textContent = `${CLUSTER_LABELS[cluster]} · ${count}`;
      }
    };
    refreshClusterCounts();

    const updateClusterLabels = () => {
      const cameraDistance = camera.position.length();
      const overview = cameraDistance > CLUSTER_LABEL_SHOW_DISTANCE;
      const closeUp = cameraDistance < CLUSTER_LABEL_HIDE_DISTANCE;
      for (const div of clusterLabelByCluster.values()) {
        if (overview) {
          div.style.opacity = "0.85";
        } else if (closeUp) {
          div.style.opacity = "0";
        }
      }
      const boxes: LabelBox[] = [];
      for (const [cluster, div] of clusterLabelByCluster) {
        const obj = clusterLabelObjectByCluster.get(cluster);
        if (!obj) continue;
        const projected = obj.getWorldPosition(new THREE.Vector3()).project(camera);
        boxes.push({
          id: cluster,
          x: ((projected.x + 1) / 2) * width,
          y: ((-projected.y + 1) / 2) * height,
          width: div.offsetWidth || 160,
          height: div.offsetHeight || 22,
        });
      }
      for (const box of resolveLabelCollisions(boxes)) {
        const div = clusterLabelByCluster.get(box.id as ClusterId);
        if (div) div.style.transform = `translate(calc(-50% + ${box.dx ?? 0}px), calc(-50% + ${box.dy ?? 0}px))`;
      }
    };

    // ----- Build node meshes -----
    const nodeGroup = new THREE.Group();
    scene.add(nodeGroup);

    const sphereGeom = new THREE.SphereGeometry(NODE_RADIUS, 14, 14);
    const ringGeom = new THREE.TorusGeometry(NODE_RADIUS * 1.6, 0.035, 6, 40);
    const meshById = new Map<string, THREE.Mesh>();
    const spriteById = new Map<string, THREE.Sprite>();
    const ringById = new Map<string, THREE.Mesh<THREE.TorusGeometry, THREE.MeshBasicMaterial>>();
    const labelByNodeId = new Map<string, HTMLDivElement>();
    const labelVisibleByNodeId = new Map<string, boolean>();
    const nodeById = new Map(simData.nodes.map((node) => [node.id, node]));
    const neighborIds = new Map<string, Set<string>>();

    const addNodeMesh = (n: SimNode, entity?: Entity): THREE.Mesh => {
      const color = new THREE.Color(colorForType(n.type));
      const importance = compositeImportance(entity);
      const mat = new THREE.MeshStandardMaterial({
        color,
        emissive: color,
        emissiveIntensity: BASE_NODE_EMISSIVE + importance * NODE_EMISSIVE_IMPORTANCE_BOOST,
        roughness: 0.4,
        metalness: 0.1,
        transparent: true,
      });
      const mesh = new THREE.Mesh(sphereGeom, mat);
      mesh.position.set(n.x ?? 0, n.y ?? 0, n.z ?? 0);
      mesh.scale.setScalar(1 + importance * NODE_RADIUS_IMPORTANCE_BOOST);
      mesh.userData = { id: n.id, type: n.type };
      nodeGroup.add(mesh);
      meshById.set(n.id, mesh);
      const sprite = new THREE.Sprite(createNodeSpriteMaterial(color));
      sprite.position.copy(mesh.position);
      sprite.scale.setScalar(NODE_RADIUS * 5);
      sprite.visible = false;
      sprite.userData = { id: n.id, type: n.type };
      nodeGroup.add(sprite);
      spriteById.set(n.id, sprite);

      if (entity) {
        const labelDiv = document.createElement("div");
        labelDiv.className = "axiom-label";
        labelDiv.textContent = displayLabelFor(entity);
        labelDiv.style.display = "block";
        labelDiv.style.opacity = "0";
        labelDiv.style.transition = "opacity 250ms ease-out";
        labelDiv.style.transform = "translate(-50%, -130%)";
        labelDiv.style.whiteSpace = "nowrap";
        labelDiv.style.maxWidth = "200px";
        labelDiv.style.overflow = "hidden";
        labelDiv.style.textOverflow = "ellipsis";
        labelDiv.style.pointerEvents = "none";
        labelDiv.style.userSelect = "none";
        labelDiv.style.fontVariantNumeric = "tabular-nums";
        labelDiv.style.letterSpacing = "0.02em";
        const labelObj = new CSS2DObject(labelDiv);
        labelObj.position.set(0, NODE_RADIUS * 1.45, 0);
        mesh.add(labelObj);
        labelByNodeId.set(n.id, labelDiv);
        labelVisibleByNodeId.set(n.id, false);
      }

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
      return mesh;
    };

    for (const n of simData.nodes) {
      addNodeMesh(n, entities.get(n.id));
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
    const edgeColors = new Float32Array(edgeCount * 2 * 4);
    const edgeGeom = new THREE.BufferGeometry();
    edgeGeom.setAttribute("position", new THREE.BufferAttribute(edgePositions, 3));
    edgeGeom.setAttribute("color", new THREE.BufferAttribute(edgeColors, 4));
    edgeGeom.setDrawRange(0, edgeCount * 2);
    const edgeMat = createEdgeShimmerMaterial();
    const edgeLines = new THREE.LineSegments(edgeGeom, edgeMat);
    scene.add(edgeLines);
    const edgeKeys = simData.links.map((link) => link.id);
    const edgeRelationships = simData.links.map((link) => link.relationship);
    const edgePhases = new Map(edgeKeys.map((key) => [key, phaseOffsetFromEdgeKey(key)]));
    const crossClusterByIndex: boolean[] = simData.links.map((link) => {
      const sourceId = typeof link.source === "string" ? link.source : link.source.id;
      const targetId = typeof link.target === "string" ? link.target : link.target.id;
      const sourceCluster = nodeById.get(sourceId)?.cluster_id;
      const targetCluster = nodeById.get(targetId)?.cluster_id;
      if (!isClusterId(sourceCluster) || !isClusterId(targetCluster)) return false;
      return sourceCluster !== targetCluster;
    });

    const refreshCrossClusterFlag = (edgeIndex: number) => {
      const link = simData.links[edgeIndex];
      if (!link) return;
      const sourceId = typeof link.source === "string" ? link.source : link.source.id;
      const targetId = typeof link.target === "string" ? link.target : link.target.id;
      const sourceCluster = nodeById.get(sourceId)?.cluster_id;
      const targetCluster = nodeById.get(targetId)?.cluster_id;
      if (!isClusterId(sourceCluster) || !isClusterId(targetCluster)) {
        crossClusterByIndex[edgeIndex] = false;
        return;
      }
      crossClusterByIndex[edgeIndex] = sourceCluster !== targetCluster;
    };

    const applyClusterEdgeStyling = () => {
      const colorAttr = edgeGeom.getAttribute("color");
      if (!(colorAttr instanceof THREE.BufferAttribute)) return;
      const colorArr = colorAttr.array as Float32Array;
      const sameRatio = SAME_CLUSTER_EDGE_OPACITY;
      const crossRatio = CROSS_CLUSTER_EDGE_OPACITY;
      for (let edgeIndex = 0; edgeIndex < simData.links.length; edgeIndex++) {
        const cross = crossClusterByIndex[edgeIndex];
        const offset = edgeIndex * 8;
        const scale = cross ? crossRatio / sameRatio : 1;
        colorArr[offset + 3] *= scale;
        colorArr[offset + 7] *= scale;
      }
      colorAttr.needsUpdate = true;
    };
    // Width is informational only — WebGL does not honour linewidth > 1
    // for line primitives — but keep the constants exported for tests.
    void SAME_CLUSTER_EDGE_WIDTH;
    void CROSS_CLUSTER_EDGE_WIDTH;
    const shouldRunSynapticFlow = (sourceId: string, targetId: string) =>
      compositeImportance(useBrainStore.getState().entities.get(sourceId)) > SYNAPTIC_FLOW_IMPORTANCE_THRESHOLD &&
      compositeImportance(useBrainStore.getState().entities.get(targetId)) > SYNAPTIC_FLOW_IMPORTANCE_THRESHOLD;

    const synapticEdges: SynapticFlowEdge[] = simData.links.flatMap((link) => {
      const sourceId = typeof link.source === "string" ? link.source : link.source.id;
      const targetId = typeof link.target === "string" ? link.target : link.target.id;
      if (!shouldRunSynapticFlow(sourceId, targetId)) return [];
      return [{ id: link.id, sourceId, targetId, relationship: link.relationship }];
    });
    const edgeShimmerSpec = {
      geom: edgeGeom,
      edgeKeys,
      edgeRelationships,
      phases: edgePhases,
    };
    const resizeEdgeBuffers = () => {
      const nextPositions = new Float32Array(simData.links.length * 2 * 3);
      const nextColors = new Float32Array(simData.links.length * 2 * 4);
      const currentPosition = edgeGeom.getAttribute("position");
      const currentColor = edgeGeom.getAttribute("color");
      if (currentPosition instanceof THREE.BufferAttribute) {
        nextPositions.set((currentPosition.array as Float32Array).subarray(0, nextPositions.length));
      }
      if (currentColor instanceof THREE.BufferAttribute) {
        nextColors.set((currentColor.array as Float32Array).subarray(0, nextColors.length));
      }
      edgeGeom.setAttribute("position", new THREE.BufferAttribute(nextPositions, 3));
      edgeGeom.setAttribute("color", new THREE.BufferAttribute(nextColors, 4));
      edgeGeom.setDrawRange(0, simData.links.length * 2);
    };

    const particleSystem = new ParticleEffectSystem();
    scene.add(particleSystem.points);
    const synapticFlow = createSynapticFlow(scene, synapticEdges, edgePhases, (edge) => {
      const source = meshById.get(edge.sourceId);
      const target = meshById.get(edge.targetId);
      if (!source || !target) return null;
      return { source: source.position, target: target.position };
    });

    let orbitalHalo: OrbitalHalo | null = null;
    let haloTargetId: string | null = null;

    const removeOrbitalHalo = () => {
      if (!orbitalHalo) return;
      scene.remove(orbitalHalo.points);
      orbitalHalo.dispose();
      orbitalHalo = null;
      haloTargetId = null;
    };

    const showSelectionHalo = (id: string) => {
      const mesh = meshById.get(id);
      if (!mesh) return;
      const meshMaterial = mesh.material;
      const color =
        meshMaterial instanceof THREE.MeshStandardMaterial ? meshMaterial.color.clone() : new THREE.Color("#FFFFFF");
      if (!orbitalHalo || haloTargetId !== id) {
        removeOrbitalHalo();
        orbitalHalo = new OrbitalHalo(color);
        scene.add(orbitalHalo.points);
      }
      orbitalHalo.setTarget(mesh.position, NODE_RADIUS * 3.2, color);
      haloTargetId = id;
    };

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
      .force("radial", forceRadial(0, 0, 0, 0).strength(0.02))
      .force("cluster", clusterGravityForce(CLUSTER_GRAVITY_DEFAULT))
      .alphaDecay(0.02)
      .velocityDecay(0.5)
      .stop();
    tuneForcesByCount(sim, simData.nodes.length);

    let simTicks = 0;
    const linkForce = sim.force("link") as { links: (links: SimLink[]) => void };
    let forceTuneTimer: number | null = null;
    const tuneForcesDebounced = () => {
      if (forceTuneTimer !== null) window.clearTimeout(forceTuneTimer);
      forceTuneTimer = window.setTimeout(() => {
        tuneForcesByCount(sim, simData.nodes.length);
        forceTuneTimer = null;
      }, 250);
    };
    const warmSimulation = (alpha: number) => {
      simTicks = 0;
      sim.alpha(Math.max(sim.alpha(), alpha));
    };

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
        const globalOverview = nodeLodMode(camera.position.length()) === "sprite";
        n.lod = globalOverview || camera.position.distanceTo(mesh.position) > FAR_LOD_DISTANCE ? "far" : "near";
        mesh.visible = n.lod === "near";
        const sprite = spriteById.get(n.id);
        if (sprite) {
          sprite.visible = n.lod === "far";
          sprite.position.copy(mesh.position);
        }
        const material = mesh.material;
        if (material instanceof THREE.MeshStandardMaterial) {
          material.opacity = n.lod === "far" ? 0.55 : 1;
        }
        const ring = ringById.get(n.id);
        if (ring) ring.position.copy(mesh.position);
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
        const visible = shouldRenderEdge(Math.floor((idx - 0) / 6), camera.position.length());
        if (!visible) {
          arr[idx++] = src.x ?? 0;
          arr[idx++] = src.y ?? 0;
          arr[idx++] = src.z ?? 0;
          arr[idx++] = src.x ?? 0;
          arr[idx++] = src.y ?? 0;
          arr[idx++] = src.z ?? 0;
          continue;
        }
        arr[idx++] = src.x ?? 0;
        arr[idx++] = src.y ?? 0;
        arr[idx++] = src.z ?? 0;
        const drawStartedAt = edgeDrawStartedAt.get(link.id);
        if (drawStartedAt !== undefined) {
          const ageMs = performance.now() - drawStartedAt;
          const source = new THREE.Vector3(src.x ?? 0, src.y ?? 0, src.z ?? 0);
          const target = new THREE.Vector3(tgt.x ?? 0, tgt.y ?? 0, tgt.z ?? 0);
          const end = edgeDrawEndpoint(source, target, ageMs);
          arr[idx++] = end.x;
          arr[idx++] = end.y;
          arr[idx++] = end.z;
          if (!isEdgeDrawActive(ageMs)) edgeDrawStartedAt.delete(link.id);
        } else {
          arr[idx++] = tgt.x ?? 0;
          arr[idx++] = tgt.y ?? 0;
          arr[idx++] = tgt.z ?? 0;
        }
      }
      posAttr.needsUpdate = true;
    };

    const applyEdgeLod = (fpsState: FpsGuardState) => {
      const colorAttr = edgeGeom.getAttribute("color");
      if (!(colorAttr instanceof THREE.BufferAttribute)) return;
      const colorArr = colorAttr.array as Float32Array;
      const farLodActive = nodeLodMode(camera.position.length()) === "sprite";
      let updated = false;
      for (let edgeIndex = 0; edgeIndex < simData.links.length; edgeIndex++) {
        const link = simData.links[edgeIndex];
        const src = typeof link.source === "object" ? link.source : undefined;
        const tgt = typeof link.target === "object" ? link.target : undefined;
        if (!src || !tgt) continue;

        const offset = edgeIndex * 8;
        const sourceId = src.id;
        const targetId = tgt.id;
        const baseAlpha = edgeOpacityForClusters(
          nodeById.get(sourceId)?.cluster_id,
          nodeById.get(targetId)?.cluster_id,
        );
        const alpha = edgeAlphaForLod(baseAlpha, fpsState, farLodActive, FAR_EDGE_ALPHA);
        colorArr[offset] = 0.45;
        colorArr[offset + 1] = 0.48;
        colorArr[offset + 2] = 0.55;
        colorArr[offset + 3] = alpha;
        colorArr[offset + 4] = 0.45;
        colorArr[offset + 5] = 0.48;
        colorArr[offset + 6] = 0.55;
        colorArr[offset + 7] = alpha;
        updated = true;
      }
      if (updated) colorAttr.needsUpdate = true;
    };

    const selectionBaseIntensity = (id: string): number => {
      const selectedId = useBrainStore.getState().selectedId;
      if (!selectedId) return nodeById.get(id)?.lod === "far" ? FAR_NODE_EMISSIVE : BASE_NODE_EMISSIVE;
      if (id === selectedId) return SELECTED_NODE_EMISSIVE;
      const selectedNeighbors = neighborIds.get(selectedId);
      if (selectedNeighbors?.has(id)) return NEIGHBOR_NODE_EMISSIVE;
      return DIMMED_NODE_EMISSIVE;
    };

    const applySelectionToEdges = () => {
      const selectedId = useBrainStore.getState().selectedId;
      if (!selectedId) return;
      const colorAttr = edgeGeom.getAttribute("color");
      if (!(colorAttr instanceof THREE.BufferAttribute)) return;
      const colorArr = colorAttr.array as Float32Array;
      for (let edgeIndex = 0; edgeIndex < simData.links.length; edgeIndex++) {
        const link = simData.links[edgeIndex];
        const sourceId = typeof link.source === "string" ? link.source : link.source.id;
        const targetId = typeof link.target === "string" ? link.target : link.target.id;
        const connectedToSelected = sourceId === selectedId || targetId === selectedId;
        const multiplier = connectedToSelected ? 1.5 : 0.4;
        const offset = edgeIndex * 8;
        colorArr[offset + 3] = Math.min(colorArr[offset + 3] * multiplier, 0.68);
        colorArr[offset + 7] = Math.min(colorArr[offset + 7] * multiplier, 0.68);
      }
      colorAttr.needsUpdate = true;
    };

    // ----- Interaction: hover rings, click focus, auto-orbit wake -----
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const hoveredIdRef = { current: null as string | null };
    const flashByNode = new Map<string, number>();
    const flashByEdge = new Map<string, number>();
    const edgeDrawStartedAt = new Map<string, number>();
    const autoOrbit = new AutoOrbitController();
    autoOrbit.notifyInteraction(0);
    let lastCameraInteractionMs = performance.now();
    let lastAutoFitThreshold = nextEntityThreshold(simData.nodes.length);
    let cameraFlight:
      | {
          startedAt: number;
          durationMs: number;
          fromPosition: THREE.Vector3;
          toPosition: THREE.Vector3;
          fromTarget: THREE.Vector3;
          toTarget: THREE.Vector3;
        }
      | null = null;
    let paletteOpen = false;

    const markCameraInteraction = (now = performance.now()) => {
      lastCameraInteractionMs = now;
      autoOrbit.notifyInteraction(now);
    };

    const startCameraFlight = (toPosition: THREE.Vector3, toTarget: THREE.Vector3, now = performance.now()) => {
      focusTargetRef.current = null;
      cameraFlight = {
        startedAt: now,
        durationMs: CAMERA_ANIMATION_MS,
        fromPosition: camera.position.clone(),
        toPosition,
        fromTarget: controls.target.clone(),
        toTarget,
      };
      markCameraInteraction(now);
    };

    const resetCamera = () => {
      startCameraFlight(INITIAL_CAMERA_POSITION.clone(), new THREE.Vector3(0, 0, 0));
    };

    const fitToView = () => {
      const box = new THREE.Box3();
      let hasPoints = false;
      for (const node of simData.nodes) {
        const point = new THREE.Vector3(node.x ?? 0, node.y ?? 0, node.z ?? 0);
        if (!Number.isFinite(point.x) || !Number.isFinite(point.y) || !Number.isFinite(point.z)) continue;
        box.expandByPoint(point);
        hasPoints = true;
      }
      if (!hasPoints) {
        resetCamera();
        return;
      }

      const center = new THREE.Vector3();
      const size = new THREE.Vector3();
      box.getCenter(center);
      box.getSize(size);

      const fov = THREE.MathUtils.degToRad(camera.fov);
      const verticalDistance = size.y / (2 * Math.tan(fov / 2));
      const horizontalDistance = size.x / (2 * Math.tan(fov / 2) * Math.max(camera.aspect, 0.1));
      const depthDistance = size.z * 0.5;
      const distance = Math.max(verticalDistance, horizontalDistance, depthDistance, 140) * 1.35 + 30;
      const direction = camera.position.clone().sub(controls.target);
      if (direction.lengthSq() < 0.001) direction.set(0, 0.2, 1);
      direction.normalize();

      camera.far = Math.max(4000, distance * 4);
      camera.updateProjectionMatrix();
      startCameraFlight(center.clone().add(direction.multiplyScalar(distance)), center);
    };

    const maybeAutoFitAfterGrowth = () => {
      const threshold = nextEntityThreshold(simData.nodes.length);
      if (threshold < AUTO_FIT_ENTITY_STEP || threshold <= lastAutoFitThreshold) return;
      lastAutoFitThreshold = threshold;
      if (performance.now() - lastCameraInteractionMs >= USER_IDLE_AUTO_FIT_MS) fitToView();
    };

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
      markCameraInteraction(ev.timeStamp);
      setPointer(ev);
      const mesh = hitNode();
      if (!mesh) {
        select(null);
        removeOrbitalHalo();
        return;
      }
      const id = (mesh.userData as { id?: string }).id;
      if (typeof id !== "string") return;
      select(id);
      focusTargetRef.current = mesh.position.clone();
      flashByNode.set(id, ev.timeStamp + 450);
      showSelectionHalo(id);
    };
    const notifyOrbitInteraction = (ev: Event) => markCameraInteraction(ev.timeStamp);
    const onKeyDown = (ev: KeyboardEvent) => {
      const target = ev.target;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) {
        return;
      }
      const key = ev.key.toLowerCase();
      if (key === "escape") {
        ev.preventDefault();
        if (useBrainStore.getState().selectedId) {
          select(null);
          removeOrbitalHalo();
        }
      }
      if (shouldResetCameraFromKey(key, paletteOpen) || key === "0") {
        ev.preventDefault();
        resetCamera();
      }
      if (key === "f") {
        ev.preventDefault();
        fitToView();
      }
    };
    const onHudResetView = () => resetCamera();
    const onPaletteState = (ev: Event) => {
      paletteOpen = Boolean((ev as CustomEvent<{ open?: boolean }>).detail?.open);
    };
    const onFlyToEntity = (ev: Event) => {
      const id = (ev as CustomEvent<{ id?: string }>).detail?.id;
      if (!id) return;
      const mesh = meshById.get(id);
      if (!mesh) return;
      select(id);
      focusTargetRef.current = null;
      flyToEntity(camera, controls, mesh.position.clone(), 1200);
      flashByNode.set(id, performance.now() + 450);
      showSelectionHalo(id);
      markCameraInteraction();
    };
    renderer.domElement.addEventListener("pointermove", onPointerMove);
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("wheel", notifyOrbitInteraction, { passive: true });
    renderer.domElement.addEventListener("touchstart", notifyOrbitInteraction, { passive: true });
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("axiom:reset-view", onHudResetView);
    window.addEventListener("axiom:fly-to-entity", onFlyToEntity);
    window.addEventListener("axiom:palette-state", onPaletteState);

    // ----- Render loop -----
    const fps = new RollingFpsCounter(60);
    const fpsGuard = new FpsGuard();
    const pulseRunner = new IdlePulseRunner();
    let raf = 0;
    let lastFrameMs = 0;
    let labelFpsState: FpsGuardState = "full";
    let labelBelowThresholdSince: number | null = null;
    let labelRecoverSince: number | null = null;
    let shimmerFrame = 0;

    const drifts = new Map<
      string,
      { from: THREE.Vector3; to: THREE.Vector3; startedAt: number; durationMs: number }
    >();

    const beginNodeDrift = (id: string, target: THREE.Vector3, durationMs: number, now = performance.now()) => {
      const node = nodeById.get(id);
      if (!node) return;
      const from = new THREE.Vector3(node.x ?? 0, node.y ?? 0, node.z ?? 0);
      drifts.set(id, { from, to: target.clone(), startedAt: now, durationMs });
    };

    const advanceDrifts = (nowMs: number) => {
      if (drifts.size === 0) return;
      for (const [id, drift] of drifts) {
        const node = nodeById.get(id);
        if (!node) {
          drifts.delete(id);
          continue;
        }
        const progress = Math.min(1, (nowMs - drift.startedAt) / Math.max(1, drift.durationMs));
        const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic
        node.x = drift.from.x + (drift.to.x - drift.from.x) * eased;
        node.y = drift.from.y + (drift.to.y - drift.from.y) * eased;
        node.z = drift.from.z + (drift.to.z - drift.from.z) * eased;
        // Hold velocity at zero while we are explicitly steering.
        node.vx = 0;
        node.vy = 0;
        node.vz = 0;
        if (progress >= 1) drifts.delete(id);
      }
    };

    const appendEntity = (entity: Entity): THREE.Mesh => {
      const [x, y, z] = envelopePosition(entity.id);
      const cluster = clusterIdFor(entity);
      const node: SimNode = { id: entity.id, type: entity.type, x, y, z, cluster_id: cluster };
      simData.nodes.push(node);
      nodeById.set(node.id, node);
      const mesh = addNodeMesh(node, entity);
      sim.nodes(simData.nodes);
      tuneForcesDebounced();
      maybeAutoFitAfterGrowth();
      warmSimulation(0.1);
      refreshClusterCounts();
      return mesh;
    };

    const appendEdge = (edge: Edge) => {
      if (simData.links.some((link) => link.id === edge.id)) return;
      const link: SimLink = {
        id: edge.id,
        source: edge.source_id,
        target: edge.target_id,
        relationship: edge.relationship,
      };
      simData.links.push(link);
      neighborIds.get(edge.source_id)?.add(edge.target_id);
      neighborIds.get(edge.target_id)?.add(edge.source_id);
      edgeKeys.push(edge.id);
      edgeRelationships.push(edge.relationship);
      edgePhases.set(edge.id, phaseOffsetFromEdgeKey(edge.id));
      crossClusterByIndex.push(false);
      refreshCrossClusterFlag(simData.links.length - 1);
      if (shouldRunSynapticFlow(edge.source_id, edge.target_id)) {
        synapticEdges.push({
          id: edge.id,
          sourceId: edge.source_id,
          targetId: edge.target_id,
          relationship: edge.relationship,
        });
      }
      resizeEdgeBuffers();
      synapticFlow.setEdges(synapticEdges);
      linkForce.links(simData.links);
      tuneForcesDebounced();
      warmSimulation(0.05);
    };

    const reclassifyNode = (id: string, clusterId: ClusterId, now: number) => {
      const node = nodeById.get(id);
      if (!node) return;
      const previous = node.cluster_id;
      node.cluster_id = clusterId;
      if (previous !== clusterId) {
        beginNodeDrift(id, CLUSTER_CENTROIDS[clusterId], NODE_DRIFT_DURATION_MS, now);
        warmSimulation(0.05);
        for (let i = 0; i < simData.links.length; i++) {
          const link = simData.links[i];
          const sourceId = typeof link.source === "string" ? link.source : link.source.id;
          const targetId = typeof link.target === "string" ? link.target : link.target.id;
          if (sourceId === id || targetId === id) refreshCrossClusterFlag(i);
        }
        refreshClusterCounts();
      }
    };

    const processLiveEvents = (nowMs: number) => {
      const deferred: BrainEvent[] = [];
      for (const event of liveEventsRef.current) {
        if ((event.type === "entity_added" || event.type === "entity_created") && event.persisted_id) {
          const payload = event.payload as Omit<Entity, "id"> & { nick?: unknown };
          const { nick: _nick, ...rest } = payload;
          void _nick;
          const entity: Entity = { id: event.persisted_id, ...rest };
          const mesh = meshById.get(event.persisted_id) ?? appendEntity(entity);
          const material = mesh.material;
          const color =
            material instanceof THREE.MeshStandardMaterial ? material.color.clone() : new THREE.Color("#FFFFFF");
          const clusterColor = arrivalColorForCluster(entity.cluster_id);
          spawnEntityArrival(particleSystem, mesh.position, new THREE.Color(clusterColor));
          particleSystem.ingestStream(mesh.position, clusterColor);
          flashByNode.set(event.persisted_id, nowMs + 600);
          continue;
        }

        if ((event.type === "edge_added" || event.type === "entity_edge_created") && event.persisted_id) {
          const payload = event.payload as Partial<Omit<Edge, "id">> & {
            relation_type?: string;
            relationship?: string;
          };
          const edge: Edge = {
            id: event.persisted_id,
            source_id: String(payload.source_id),
            target_id: String(payload.target_id),
            relationship: payload.relationship ?? payload.relation_type ?? "related",
            data: (payload.data as Record<string, unknown> | undefined) ?? {},
            created_at: typeof payload.created_at === "string" ? payload.created_at : new Date().toISOString(),
          };
          const src = meshById.get(edge.source_id);
          const tgt = meshById.get(edge.target_id);
          if (!src || !tgt) {
            deferred.push(event);
            continue;
          }
          appendEdge(edge);
          if (event.type === "entity_edge_created") edgeDrawStartedAt.set(edge.id, nowMs);
          spawnEdgeTrace(particleSystem, src.position, tgt.position, colorForRelationship(edge.relationship));
          flashByEdge.set(event.persisted_id, nowMs + 600);
          continue;
        }

        if (event.type === "entity_classified") {
          const payload = event.payload as { entity_id?: string; cluster_id?: string };
          const entityId = payload.entity_id ?? event.persisted_id;
          if (typeof entityId !== "string") continue;
          if (!isClusterId(payload.cluster_id)) continue;
          reclassifyNode(entityId, payload.cluster_id, nowMs);
          continue;
        }

        if (event.type === "entity_modified") {
          const id = event.persisted_id ?? event.source_id;
          if (typeof id !== "string") continue;
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

    const updateLabelFpsState = (currentFps: number, nowMs: number) => {
      if (currentFps < LABEL_FPS_HIDE_THRESHOLD) {
        labelBelowThresholdSince ??= nowMs;
        labelRecoverSince = null;
        if (nowMs - labelBelowThresholdSince >= 5000) {
          labelFpsState = "emergency";
        }
        return;
      }

      labelBelowThresholdSince = null;
      if (labelFpsState === "emergency") {
        if (currentFps > LABEL_FPS_RECOVER_THRESHOLD) {
          labelRecoverSince ??= nowMs;
          if (nowMs - labelRecoverSince >= 3000) {
            labelFpsState = "full";
          }
        } else {
          labelRecoverSince = null;
        }
        return;
      }

      labelFpsState = fpsGuard.state();
    };

    const updateLabelVisibility = () => {
      const selectedId = useBrainStore.getState().selectedId;
      const selectedNeighborIds = selectedId ? (neighborIds.get(selectedId) ?? new Set<string>()) : new Set<string>();
      const alwaysVisibleIds = new Set<string>();
      if (selectedId) {
        alwaysVisibleIds.add(selectedId);
        for (const neighborId of selectedNeighborIds) alwaysVisibleIds.add(neighborId);
      }
      const candidates: Array<{ nodeId: string; labelDiv: HTMLDivElement; importance: number; visible: boolean }> = [];

      for (const [nodeId, labelDiv] of labelByNodeId) {
        const mesh = meshById.get(nodeId);
        if (!mesh) continue;
        const isAlwaysVisible = alwaysVisibleIds.has(nodeId);
        const baseVisible =
          shouldShowLabel({
            nodeId,
            cameraDistance: camera.position.length(),
            selectedId,
            selectedNeighborIds,
            fpsGuardState: labelFpsState,
            currentlyVisible: labelVisibleByNodeId.get(nodeId) ?? false,
            showDistance: LABEL_SHOW_DISTANCE_MAX,
            hideDistance: LABEL_SHOW_DISTANCE_MAX,
          }) && (isAlwaysVisible || (nodeById.get(nodeId)?.lod ?? "near") === "near");

        if (isAlwaysVisible) {
          labelVisibleByNodeId.set(nodeId, baseVisible);
          labelDiv.style.opacity = baseVisible ? "1" : "0";
          continue;
        }

        candidates.push({
          nodeId,
          labelDiv,
          importance: labelImportance(useBrainStore.getState().entities.get(nodeId), neighborIds.get(nodeId)?.size ?? 0),
          visible: baseVisible,
        });
      }

      const cappedVisible = new Set(
        candidates
          .filter((candidate) => candidate.visible)
          .sort((a, b) => b.importance - a.importance || a.nodeId.localeCompare(b.nodeId))
          .slice(0, LABEL_OVERVIEW_CAP)
          .map((candidate) => candidate.nodeId),
      );

      for (const candidate of candidates) {
        const visible = cappedVisible.has(candidate.nodeId);
        labelVisibleByNodeId.set(candidate.nodeId, visible);
        candidate.labelDiv.style.opacity = visible ? "1" : "0";
      }
    };

    const hideAllLabels = () => {
      for (const labelDiv of labelByNodeId.values()) {
        labelDiv.style.opacity = "0";
      }
      for (const nodeId of labelVisibleByNodeId.keys()) {
        labelVisibleByNodeId.set(nodeId, false);
      }
    };

    const updateHoverAndRings = () => {
      const hoveredId = hoveredIdRef.current;
      const selectedId = useBrainStore.getState().selectedId;
      const activeNeighbors = hoveredId ? neighborIds.get(hoveredId) : null;
      const selectedNeighbors = selectedId ? neighborIds.get(selectedId) : null;
      const stateEntities = useBrainStore.getState().entities;
      for (const [id, mesh] of meshById) {
        const lodScale = nodeById.get(id)?.lod === "far" ? FAR_NODE_SCALE : 1;
        const isSelected = id === selectedId;
        const importance = compositeImportance(stateEntities.get(id));
        const importanceScale = 1 + importance * NODE_RADIUS_IMPORTANCE_BOOST;
        const targetScale =
          (isSelected ? 1.14 : id === hoveredId ? 1.2 : 1) * lodScale * importanceScale;
        const nextScale = mesh.scale.x + (targetScale - mesh.scale.x) * 0.15;
        mesh.scale.setScalar(nextScale);

        const ring = ringById.get(id);
        if (!ring) continue;
        if (lodScale < 1) {
          ring.visible = false;
          ring.material.opacity = 0;
          continue;
        }
        const isHover = id === hoveredId;
        const isNeighbor = activeNeighbors?.has(id) ?? false;
        const isSelectedNeighbor = selectedNeighbors?.has(id) ?? false;
        const targetOpacity = isSelected ? 0.7 : isHover ? 0.45 : isSelectedNeighbor ? 0.28 : isNeighbor ? 0.18 : 0;
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
          material.emissiveIntensity += ((until - nowMs) / 600) * 0.25;
        }
      }

      const colorAttr = edgeGeom.getAttribute("color");
      if (!(colorAttr instanceof THREE.BufferAttribute)) return;
      const colorArr = colorAttr.array as Float32Array;
      simData.links.forEach((link, i) => {
        const until = flashByEdge.get(link.id);
        if (until === undefined) return;
        if (nowMs > until) {
          flashByEdge.delete(link.id);
          return;
        }
        const alpha = 0.28 * ((until - nowMs) / 600);
        colorArr[i * 8 + 3] = Math.max(colorArr[i * 8 + 3], alpha);
        colorArr[i * 8 + 7] = Math.max(colorArr[i * 8 + 7], alpha);
      });
      colorAttr.needsUpdate = true;
    };

    const tick = (t: number) => {
      const dtMs = lastFrameMs === 0 ? 16.7 : t - lastFrameMs;
      lastFrameMs = t;
      processLiveEvents(t);
      stepSim();
      advanceDrifts(t);
      syncPositions();
      nebula.update(t);
      updateClusterAuras(clusterAuras, t);
      const cameraDistance = camera.position.length();
      setAurasVisible(clusterAuras, cameraDistance <= 280);
      bloomPass.strength = bloomStrengthForDistance(cameraDistance);
      const fpsState = fpsGuard.state();
      if (fpsState !== "emergency") {
        pulseRunner.update(
          meshById,
          t,
          (id) => selectionBaseIntensity(id),
          (id) => compositeImportance(useBrainStore.getState().entities.get(id)) > IDLE_PULSE_IMPORTANCE_THRESHOLD,
        );
      }
      try {
        shimmerFrame++;
        const selectionActive = useBrainStore.getState().selectedId !== null;
        if (selectionActive || fpsState === "full" || (fpsState === "half" && shimmerFrame % 2 === 0)) {
          updateEdgeShimmer(edgeShimmerSpec, t);
        }
        applyClusterEdgeStyling();
        applyEdgeLod(fpsState);
        applySelectionToEdges();
        updateSynapticFlow(t, dtMs, fpsState);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("[Brain] edge activity update failed:", err);
      }
      updateHoverAndRings();
      updateFlashes(t);
      particleSystem.setParticleMultiplier(fpsGuard.particleMultiplier());
      particleSystem.update(t);
      const selectedId = useBrainStore.getState().selectedId;
      if (selectedId) {
        showSelectionHalo(selectedId);
      } else {
        removeOrbitalHalo();
      }
      orbitalHalo?.update(t);

      const v = fps.tick(t);
      if (v) {
        setFps(v);
        fpsGuard.sample(v, t);
        updateLabelFpsState(v, t);
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

      if (cameraFlight) {
        const progress = Math.min(1, (t - cameraFlight.startedAt) / cameraFlight.durationMs);
        const eased = easeInOutCubic(progress);
        camera.position.lerpVectors(cameraFlight.fromPosition, cameraFlight.toPosition, eased);
        controls.target.lerpVectors(cameraFlight.fromTarget, cameraFlight.toTarget, eased);
        if (progress >= 1) cameraFlight = null;
      }

      autoOrbit.applyToCamera(camera, t, dtMs);
      try {
        updateClusterLabels();
        const labelsAllowed =
          fpsState === "full" &&
          (simData.nodes.length <= LABEL_OVERVIEW_ENTITY_LIMIT || useBrainStore.getState().selectedId !== null);
        if (labelsAllowed) {
          updateLabelVisibility();
        } else {
          hideAllLabels();
        }
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("[Brain] label visibility update failed:", err);
      }
      controls.update();
      composer.render();
      try {
        const labelsAllowed =
          fpsState === "full" &&
          (simData.nodes.length <= LABEL_OVERVIEW_ENTITY_LIMIT || useBrainStore.getState().selectedId !== null);
        if (labelsAllowed) labelRenderer.render(scene, camera);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("[Brain] label render failed:", err);
      }
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
      labelRenderer.setSize(w, h);
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
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("axiom:reset-view", onHudResetView);
      window.removeEventListener("axiom:fly-to-entity", onFlyToEntity);
      window.removeEventListener("axiom:palette-state", onPaletteState);
      if (forceTuneTimer !== null) window.clearTimeout(forceTuneTimer);
      sim.stop();
      controls.dispose();
      composer.dispose();
      nebula.dispose();
      particleSystem.dispose();
      disposeSynapticFlow();
      orbitalHalo?.dispose();
      renderer.dispose();
      sphereGeom.dispose();
      ringGeom.dispose();
      edgeGeom.dispose();
      edgeMat.dispose();
      labelByNodeId.clear();
      labelVisibleByNodeId.clear();
      clusterLabelByCluster.clear();
      clusterLabelObjectByCluster.clear();
      clusterCountByCluster.clear();
      meshById.forEach((m) => {
        (m.material as THREE.Material).dispose();
      });
      ringById.forEach((r) => {
        r.material.dispose();
      });
      spriteById.forEach((s) => {
        s.material.dispose();
      });
      clusterAuras.forEach((aura) => {
        scene.remove(aura);
        aura.geometry.dispose();
        aura.material.dispose();
      });
      if (renderer.domElement.parentNode === el) {
        el.removeChild(renderer.domElement);
      }
      if (labelRenderer.domElement.parentNode === el) {
        el.removeChild(labelRenderer.domElement);
      }
    };
  }, [sceneReady, select, setFps]);

  return <div ref={containerRef} className="absolute inset-0" aria-hidden="true" />;
}
