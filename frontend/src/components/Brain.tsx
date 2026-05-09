import * as THREE from "three";
import { useEffect, useRef, useState } from "react";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { CSS2DObject, CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";

import {
  bracketLinePoints,
  clusterLabelAnchor,
  createClusterBracketElement,
  updateClusterBracketElement,
} from "@/components/ClusterBracketLabel";
import { easeInOutCubic, shouldResetCameraFromKey } from "@/lib/camera-reset";
import {
  CLUSTER_COLORS,
  CLUSTER_IDS,
  CLUSTER_RADIUS,
  CLUSTER_CENTROIDS,
  isClusterId,
  type ClusterId,
} from "@/lib/cluster-layout";
import { superClusterIdForEntity } from "@/lib/cluster-reframe";
import { conduitPathsForEdges, createConduitLine, type ConduitPath } from "@/lib/curved-conduits";
import { RollingFpsCounter } from "@/lib/fps";
import { createHexGridPlane, createStarField } from "@/lib/hex-grid-bg";
import { createHexPrismGeometry, HEX_HEIGHT, HEX_HUB_RADIUS, HEX_NODE_RADIUS } from "@/lib/hex-geometry";
import {
  computeVisibleEntitySlots,
  entityImportance,
  findEntityPosition,
  sortedVisibleEntities,
  type InterHubEdge,
  type VisibleEntitySlot,
} from "@/lib/hex-layout";
import { IdleOrbitController } from "@/lib/idle-orbit";
import { ParticleFlowController } from "@/lib/particle-flow";
import { hashStringToFloat, hubEmissiveIntensityAt, shimmerScale } from "@/lib/spoke-shimmer";
import { hasWebGPU, preferredRendererKind } from "@/lib/webgpu-detect";
import { BrainSocket, type BrainEvent } from "@/lib/websocket";
import { useBrainStore, type ClusterHealthSnapshot, type Edge, type Entity } from "@/state/brain.store";

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as T;
}

const SCENE_TARGET = new THREE.Vector3(10, 12, 0);
const INITIAL_CAMERA_POSITION = new THREE.Vector3(10, 12, 205);
const CAMERA_ANIMATION_MS = 800;
const HUB_EMISSIVE = 2;
const MIN_VISIBLE_PER_CLUSTER = 6;
const VISUAL_CAPS: Record<ClusterId, number> = {
  company_knowledge: 60,
  execution_context: 56,
  customers: 9,
  policies: 9,
  receipts: 8,
  agents: 9,
  incidents: 9,
  governance: 9,
  people_teams: 8,
  billing: 9,
};
const LABELED_CLUSTERS = new Set<ClusterId>([
  "company_knowledge",
  "execution_context",
  "customers",
  "policies",
  "receipts",
  "agents",
  "incidents",
  "governance",
]);
const VISUAL_CLUSTER_IDS: readonly ClusterId[] = [
  "customers",
  "policies",
  "receipts",
  "company_knowledge",
  "execution_context",
  "agents",
  "incidents",
  "governance",
];

function reframe(entity: Entity): Entity {
  return { ...entity, cluster_id: superClusterIdForEntity(entity) ?? entity.cluster_id ?? "company_knowledge" };
}

function titleForEntity(entity: Entity): string {
  for (const key of ["title", "name", "subject", "label", "file_path"]) {
    const value = entity.data?.[key];
    if (typeof value === "string" && value.trim()) return key === "file_path" ? (value.split("/").pop() ?? value) : value;
  }
  return entity.id;
}

function syntheticEntity(cluster: ClusterId, index: number): Entity {
  return {
    id: `synthetic-${cluster}-${index}`,
    type: cluster === "agents" ? "agent" : cluster === "receipts" ? "receipt" : cluster === "governance" ? "governance" : "entity",
    cluster_id: cluster,
    source_id: null,
    created_at: new Date(0).toISOString(),
    updated_at: new Date(0).toISOString(),
    composite_importance: 0.35 + index * 0.02,
    data: {
      title: `${cluster.replace(/_/g, " ")} signal ${index + 1}`,
      description: "Visual placeholder synthesized from aggregate cluster metadata.",
      synthetic: true,
    },
  };
}

function visualEntities(realEntities: Iterable<Entity>): Entity[] {
  const byCluster = new Map<ClusterId, Entity[]>();
  for (const cluster of VISUAL_CLUSTER_IDS) byCluster.set(cluster, []);
  for (const entity of realEntities) {
    const reframed = reframe(entity);
    if (isClusterId(reframed.cluster_id)) byCluster.get(reframed.cluster_id)?.push(reframed);
  }

  const out: Entity[] = [];
  for (const cluster of VISUAL_CLUSTER_IDS) {
    const cap = VISUAL_CAPS[cluster];
    const selected = sortedVisibleEntities(byCluster.get(cluster) ?? [], cap);
    out.push(...selected);
    for (let i = selected.length; i < Math.min(MIN_VISIBLE_PER_CLUSTER, cap); i++) {
      out.push(syntheticEntity(cluster, i));
    }
  }
  return out;
}

function entityCounts(realEntities: Iterable<Entity>, health: Record<string, ClusterHealthSnapshot>): Map<ClusterId, number> {
  const counts = new Map<ClusterId, number>();
  for (const cluster of CLUSTER_IDS) counts.set(cluster, 0);
  for (const entity of realEntities) {
    const cluster = superClusterIdForEntity(entity);
    if (cluster) counts.set(cluster, (counts.get(cluster) ?? 0) + 1);
  }
  for (const cluster of CLUSTER_IDS) {
    if ((counts.get(cluster) ?? 0) === 0) counts.set(cluster, Math.max(health[cluster]?.total_entities ?? 0, MIN_VISIBLE_PER_CLUSTER));
  }
  return counts;
}

function relationshipCounts(edges: Iterable<Edge>, entitiesById: Map<string, Entity>): Map<ClusterId, number> {
  const counts = new Map<ClusterId, number>();
  for (const cluster of CLUSTER_IDS) counts.set(cluster, 0);
  for (const edge of edges) {
    const sourceEntity = entitiesById.get(edge.source_id);
    const targetEntity = entitiesById.get(edge.target_id);
    const sourceCluster = isClusterId(sourceEntity?.cluster_id) ? sourceEntity.cluster_id : superClusterIdForEntity(sourceEntity);
    const targetCluster = isClusterId(targetEntity?.cluster_id) ? targetEntity.cluster_id : superClusterIdForEntity(targetEntity);
    if (sourceCluster) counts.set(sourceCluster, (counts.get(sourceCluster) ?? 0) + 1);
    if (targetCluster && targetCluster !== sourceCluster) counts.set(targetCluster, (counts.get(targetCluster) ?? 0) + 1);
  }
  return counts;
}

function labelAnchorForCluster(cluster: ClusterId): THREE.Vector3 {
  const hub = CLUSTER_CENTROIDS[cluster];
  const overrides: Partial<Record<ClusterId, THREE.Vector3>> = {
    company_knowledge: new THREE.Vector3(-78, 28, 5),
    execution_context: new THREE.Vector3(25, 44, 0),
    policies: new THREE.Vector3(-72, 76, 14),
    customers: new THREE.Vector3(-140, 8, 10),
    receipts: new THREE.Vector3(-96, -28, 5),
    agents: new THREE.Vector3(70, 80, -4),
    incidents: new THREE.Vector3(108, 24, 5),
    governance: new THREE.Vector3(82, -8, 0),
  };
  if (overrides[cluster]) return overrides[cluster]!.clone();
  const offset = CLUSTER_RADIUS[cluster] + 22;
  const anchor = clusterLabelAnchor(hub, offset);
  if (anchor.x > 88) anchor.x = hub.x - offset;
  if (anchor.x < -95) anchor.x = hub.x + offset;
  if (anchor.y > 52) anchor.y = hub.y - offset * 0.55;
  if (anchor.y < -52) anchor.y = hub.y + offset * 0.55;
  return anchor;
}

function makeHaloTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 62);
    gradient.addColorStop(0, "rgba(255,255,255,0.85)");
    gradient.addColorStop(0.3, "rgba(255,255,255,0.28)");
    gradient.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 128, 128);
  }
  return new THREE.CanvasTexture(canvas);
}

function createIntraClusterWeb(slots: VisibleEntitySlot[]): THREE.LineSegments {
  const points: THREE.Vector3[] = [];
  for (const cluster of VISUAL_CLUSTER_IDS) {
    const clusterSlots = slots.filter((slot) => slot.clusterId === cluster);
    for (let i = 0; i < clusterSlots.length; i++) {
      const here = clusterSlots[i];
      const nearest = clusterSlots
        .filter((_, index) => index !== i)
        .map((slot) => ({ slot, distance: here.position.distanceTo(slot.position) }))
        .sort((a, b) => a.distance - b.distance)
        .slice(0, i % 3 === 0 ? 2 : 1);
      for (const item of nearest) {
        points.push(here.position, item.slot.position);
      }
    }
  }
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  const material = new THREE.LineBasicMaterial({
    color: "#4DD3B8",
    transparent: true,
    opacity: 0.08,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  return new THREE.LineSegments(geometry, material);
}

function createConduitLines(paths: ConduitPath[]): { group: THREE.Group; linesByKey: Map<string, THREE.Line> } {
  const group = new THREE.Group();
  const linesByKey = new Map<string, THREE.Line>();
  for (const path of paths) {
    const line = createConduitLine(path);
    group.add(line);
    linesByKey.set(path.key, line);
  }
  return { group, linesByKey };
}

function referenceHubEdges(): InterHubEdge[] {
  return [
    { key: "customers:company_knowledge", sourceCluster: "customers", targetCluster: "company_knowledge", weight: 8 },
    { key: "policies:company_knowledge", sourceCluster: "policies", targetCluster: "company_knowledge", weight: 7 },
    { key: "receipts:company_knowledge", sourceCluster: "receipts", targetCluster: "company_knowledge", weight: 6 },
    { key: "company_knowledge:execution_context", sourceCluster: "company_knowledge", targetCluster: "execution_context", weight: 14 },
    { key: "execution_context:agents", sourceCluster: "execution_context", targetCluster: "agents", weight: 7 },
    { key: "execution_context:incidents", sourceCluster: "execution_context", targetCluster: "incidents", weight: 8 },
    { key: "execution_context:governance", sourceCluster: "execution_context", targetCluster: "governance", weight: 6 },
  ];
}

function composeNodeTransform(
  mesh: THREE.InstancedMesh,
  index: number,
  slot: VisibleEntitySlot,
  selectedId: string | null,
  hoveredId: string | null,
  now: number,
): void {
  const matrix = new THREE.Matrix4();
  const scaleValue =
    (slot.hexRadius / HEX_NODE_RADIUS) *
    THREE.MathUtils.lerp(0.9, 1.25, entityImportance(slot.entity)) *
    (slot.entity.id === selectedId ? 1.18 : 1) *
    (slot.entity.id === hoveredId ? 1.15 : 1) *
    shimmerScale(hashStringToFloat(slot.entity.id), now);
  matrix.compose(slot.position, new THREE.Quaternion(), new THREE.Vector3(scaleValue, scaleValue, scaleValue));
  mesh.setMatrixAt(index, matrix);
}

export function Brain() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const liveEventsRef = useRef<BrainEvent[]>([]);
  const [sceneReady, setSceneReady] = useState(false);

  const bootstrap = useBrainStore((s) => s.bootstrap);
  const setClusterHealth = useBrainStore((s) => s.setClusterHealth);
  const setConnectionStatus = useBrainStore((s) => s.setConnectionStatus);
  const applyEvent = useBrainStore((s) => s.applyEvent);
  const setFps = useBrainStore((s) => s.setFps);
  const select = useBrainStore((s) => s.select);
  const selectCluster = useBrainStore((s) => s.selectCluster);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [ents, eds, health] = await Promise.all([
          fetchJson<unknown[]>("http://127.0.0.1:8000/api/entities"),
          fetchJson<unknown[]>("http://127.0.0.1:8000/api/edges"),
          fetchJson<Record<string, ClusterHealthSnapshot>>("http://127.0.0.1:8000/api/cluster_health").catch(() => ({})),
        ]);
        if (cancelled) return;
        bootstrap(ents as Entity[], eds as Edge[]);
        setClusterHealth(health);
        setSceneReady(true);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("[Brain] bootstrap failed:", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [bootstrap, setClusterHealth]);

  useEffect(() => {
    const url = `ws://${window.location.hostname}:8000/ws/brain`;
    const ws = new BrainSocket(url);
    setConnectionStatus("syncing");
    const off = ws.on((event) => {
      liveEventsRef.current.push(event);
      applyEvent(event);
      window.dispatchEvent(new CustomEvent("axiom:brain-event", { detail: event }));
    });
    const offStatus = ws.onStatus(setConnectionStatus);
    ws.start();
    return () => {
      off();
      offStatus();
      ws.close();
    };
  }, [applyEvent, setConnectionStatus]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !sceneReady) return;

    const state = useBrainStore.getState();
    const entities = new Map(state.entities);
    const edges = new Map(state.edges);
    const entitiesById = () => new Map(Array.from(entities.values(), reframe).map((entity) => [entity.id, entity]));
    let slots = computeVisibleEntitySlots(visualEntities(entities.values()), VISUAL_CLUSTER_IDS, 60, CLUSTER_CENTROIDS);
    let interHubEdges = referenceHubEdges();
    let conduitPaths = conduitPathsForEdges(interHubEdges, CLUSTER_CENTROIDS);
    const positionsById = new Map(slots.map((slot) => [slot.entity.id, slot.position.clone()]));
    const idByInstanceIndex = slots.map((slot) => slot.entity.id);

    const width = el.clientWidth || window.innerWidth;
    const height = el.clientHeight || window.innerHeight;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#05050A");

    const grid = createHexGridPlane();
    scene.add(grid);
    const stars = createStarField();
    scene.add(stars.points);

    const camera = new THREE.PerspectiveCamera(44, width / height, 1, 4000);
    camera.position.copy(INITIAL_CAMERA_POSITION);
    const ambient = new THREE.AmbientLight(0xffffff, 0.32);
    scene.add(ambient);
    const keyLight = new THREE.DirectionalLight(0xddeeff, 0.85);
    keyLight.position.set(0.5, 1, 2);
    scene.add(keyLight);

    type WebGpuRendererCtor = new (opts: { antialias: boolean; alpha: boolean }) => THREE.WebGLRenderer;
    const maybeThree = THREE as unknown as { WebGPURenderer?: WebGpuRendererCtor };
    const kind = preferredRendererKind({
      navigatorHasWebGpu: hasWebGPU(),
      threeHasWebGpuRenderer: typeof maybeThree.WebGPURenderer !== "undefined",
    });
    let renderer: THREE.WebGLRenderer;
    try {
      renderer =
        kind === "webgpu" && maybeThree.WebGPURenderer
          ? new maybeThree.WebGPURenderer({ antialias: true, alpha: false })
          : new THREE.WebGLRenderer({ antialias: true, alpha: false });
    } catch {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    }
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.8));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.92;
    el.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 54;
    controls.maxDistance = 400;
    controls.target.copy(SCENE_TARGET);
    const idleOrbit = new IdleOrbitController(camera, controls);

    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloomPass = new UnrealBloomPass(new THREE.Vector2(width, height), 0.8, 0.5, 0.15);
    composer.addPass(bloomPass);

    const labelRenderer = new CSS2DRenderer();
    labelRenderer.setSize(width, height);
    labelRenderer.domElement.classList.add("axiom-labels");
    labelRenderer.domElement.style.position = "absolute";
    labelRenderer.domElement.style.inset = "0";
    labelRenderer.domElement.style.pointerEvents = "none";
    el.appendChild(labelRenderer.domElement);

    const labelObjects = new Map<ClusterId, CSS2DObject>();
    const labelDivs = new Map<ClusterId, HTMLDivElement>();
    const refreshLabels = () => {
      const counts = entityCounts(entities.values(), useBrainStore.getState().clusterHealth);
      const relationships = relationshipCounts(edges.values(), entitiesById());
      for (const cluster of VISUAL_CLUSTER_IDS) {
        const div = labelDivs.get(cluster);
        if (div) {
          updateClusterBracketElement(div, cluster, counts.get(cluster) ?? 0, {
            entities: counts.get(cluster) ?? 0,
            relationships: relationships.get(cluster) ?? 0,
          });
        }
      }
    };
    const initialCounts = entityCounts(entities.values(), state.clusterHealth);
    const initialRelationships = relationshipCounts(edges.values(), entitiesById());
    const bracketLines = new THREE.Group();
    for (const cluster of VISUAL_CLUSTER_IDS) {
      if (!LABELED_CLUSTERS.has(cluster)) continue;
      const div = createClusterBracketElement(cluster, initialCounts.get(cluster) ?? 0, {
        entities: initialCounts.get(cluster) ?? 0,
        relationships: initialRelationships.get(cluster) ?? 0,
      });
      const object = new CSS2DObject(div);
      object.position.copy(labelAnchorForCluster(cluster));
      scene.add(object);
      labelObjects.set(cluster, object);
      labelDivs.set(cluster, div);

      const geometry = new THREE.BufferGeometry().setFromPoints(
        bracketLinePoints(CLUSTER_CENTROIDS[cluster], object.position),
      );
      bracketLines.add(
        new THREE.Line(
          geometry,
          new THREE.LineBasicMaterial({
            color: CLUSTER_COLORS[cluster],
            transparent: true,
            opacity: 0.5,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
          }),
        ),
      );
    }
    scene.add(bracketLines);

    const haloTexture = makeHaloTexture();
    const hubGeometry = createHexPrismGeometry(HEX_HUB_RADIUS, HEX_HEIGHT * 1.5);
    const hubMeshes = new Map<ClusterId, THREE.Mesh<THREE.CylinderGeometry, THREE.MeshStandardMaterial>>();
    const hubCores: THREE.Mesh[] = [];
    const hubHalos: THREE.Sprite[] = [];
    for (const cluster of VISUAL_CLUSTER_IDS) {
      const color = new THREE.Color(CLUSTER_COLORS[cluster]);
      const hub = new THREE.Mesh(
        hubGeometry,
        new THREE.MeshStandardMaterial({
          color,
          emissive: color,
          emissiveIntensity: HUB_EMISSIVE,
          metalness: 0.32,
          roughness: 0.28,
        }),
      );
      hub.position.copy(CLUSTER_CENTROIDS[cluster]);
      hub.userData = { cluster };
      hubMeshes.set(cluster, hub);
      scene.add(hub);

      const core = new THREE.Mesh(
        new THREE.SphereGeometry(1.6, 16, 16),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending }),
      );
      core.position.copy(CLUSTER_CENTROIDS[cluster]);
      hubCores.push(core);
      scene.add(core);

      const halo = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: haloTexture,
          color,
          transparent: true,
          opacity: cluster === "company_knowledge" || cluster === "execution_context" ? 0.28 : 0.2,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        }),
      );
      const haloScale = (CLUSTER_RADIUS[cluster] + 10) * 1.55;
      halo.scale.set(haloScale, haloScale, 1);
      halo.position.copy(CLUSTER_CENTROIDS[cluster]).add(new THREE.Vector3(0, 0, -1));
      hubHalos.push(halo);
      scene.add(halo);
    }

    const nodeGeometry = createHexPrismGeometry(HEX_NODE_RADIUS, HEX_HEIGHT);
    const nodeMaterial = new THREE.MeshBasicMaterial({
      color: "#ffffff",
      transparent: true,
      opacity: 0.82,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const nodeMesh = new THREE.InstancedMesh(nodeGeometry, nodeMaterial, Math.max(slots.length, 1));
    nodeMesh.count = slots.length;
    nodeMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    for (let i = 0; i < slots.length; i++) {
      composeNodeTransform(nodeMesh, i, slots[i], null, null, 0);
      nodeMesh.setColorAt(i, new THREE.Color(CLUSTER_COLORS[slots[i].clusterId]).lerp(new THREE.Color("#E8F0FF"), 0.16));
    }
    nodeMesh.instanceColor?.setUsage(THREE.DynamicDrawUsage);
    if (nodeMesh.instanceColor) nodeMesh.instanceColor.needsUpdate = true;
    scene.add(nodeMesh);

    let intraWeb = createIntraClusterWeb(slots);
    scene.add(intraWeb);

    let { group: interHubLines, linesByKey } = createConduitLines(conduitPaths);
    scene.add(interHubLines);
    const particleFlow = new ParticleFlowController(conduitPaths);
    scene.add(particleFlow.points);

    const selectionRing = new THREE.Mesh(
      new THREE.TorusGeometry(HEX_NODE_RADIUS * 2.2, 0.055, 6, 48),
      new THREE.MeshBasicMaterial({
        color: "#E8F0FF",
        transparent: true,
        opacity: 0.75,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    selectionRing.visible = false;
    scene.add(selectionRing);

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const hoveredIdRef = { current: null as string | null };
    let paletteOpen = false;
    let cameraFlight:
      | {
          startedAt: number;
          fromPosition: THREE.Vector3;
          toPosition: THREE.Vector3;
          fromTarget: THREE.Vector3;
          toTarget: THREE.Vector3;
        }
      | null = null;
    const traversalTimers: number[] = [];

    const startCameraFlight = (toTarget: THREE.Vector3, distance = 62, now = performance.now()) => {
      idleOrbit.noteUserInput(now);
      const direction = new THREE.Vector3(0, 0.12, 1).normalize();
      cameraFlight = {
        startedAt: now,
        fromPosition: camera.position.clone(),
        toPosition: toTarget.clone().addScaledVector(direction, distance),
        fromTarget: controls.target.clone(),
        toTarget: toTarget.clone(),
      };
    };
    const resetCamera = () => {
      select(null);
      startCameraFlight(SCENE_TARGET, 205);
    };
    const setPointer = (ev: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
    };
    const hitNodeId = (): string | null => {
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObject(nodeMesh, false)[0];
      return typeof hit?.instanceId === "number" ? (idByInstanceIndex[hit.instanceId] ?? null) : null;
    };
    const hitHubCluster = (): ClusterId | null => {
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(Array.from(hubMeshes.values()), false)[0];
      return isClusterId(hit?.object.userData.cluster) ? hit.object.userData.cluster : null;
    };
    const syncSlots = () => {
      slots = computeVisibleEntitySlots(visualEntities(entities.values()), VISUAL_CLUSTER_IDS, 60, CLUSTER_CENTROIDS);
      positionsById.clear();
      idByInstanceIndex.length = 0;
      nodeMesh.count = slots.length;
      for (let i = 0; i < slots.length; i++) {
        positionsById.set(slots[i].entity.id, slots[i].position.clone());
        idByInstanceIndex.push(slots[i].entity.id);
        nodeMesh.setColorAt(i, new THREE.Color(CLUSTER_COLORS[slots[i].clusterId]).lerp(new THREE.Color("#E8F0FF"), 0.16));
      }
      if (nodeMesh.instanceColor) nodeMesh.instanceColor.needsUpdate = true;
      scene.remove(intraWeb);
      intraWeb.geometry.dispose();
      (intraWeb.material as THREE.Material).dispose();
      intraWeb = createIntraClusterWeb(slots);
      scene.add(intraWeb);
    };
    const rebuildConduits = () => {
      scene.remove(interHubLines);
      interHubLines.traverse((obj) => {
        if (obj instanceof THREE.Line) {
          obj.geometry.dispose();
          (obj.material as THREE.Material).dispose();
        }
      });
      interHubEdges = referenceHubEdges();
      conduitPaths = conduitPathsForEdges(interHubEdges, CLUSTER_CENTROIDS);
      const built = createConduitLines(conduitPaths);
      interHubLines = built.group;
      linesByKey = built.linesByKey;
      scene.add(interHubLines);
      particleFlow.setEdges(conduitPaths, performance.now());
    };
    const processLiveEvents = (nowMs: number) => {
      const deferred: BrainEvent[] = [];
      for (const event of liveEventsRef.current) {
        if ((event.type === "entity_added" || event.type === "entity_created") && event.persisted_id) {
          const payload = event.payload as Omit<Entity, "id"> & { nick?: unknown };
          const { nick: _nick, ...rest } = payload;
          void _nick;
          entities.set(event.persisted_id, { id: event.persisted_id, ...rest });
          syncSlots();
          refreshLabels();
          continue;
        }
        if ((event.type === "edge_added" || event.type === "entity_edge_created") && event.persisted_id) {
          const payload = event.payload as Partial<Omit<Edge, "id">> & { relation_type?: string };
          if (typeof payload.source_id !== "string" || typeof payload.target_id !== "string") {
            deferred.push(event);
            continue;
          }
          const edge: Edge = {
            id: event.persisted_id,
            source_id: payload.source_id,
            target_id: payload.target_id,
            relationship: payload.relationship ?? payload.relation_type ?? "related",
            data: (payload.data as Record<string, unknown> | undefined) ?? {},
            created_at: typeof payload.created_at === "string" ? payload.created_at : new Date().toISOString(),
          };
          edges.set(edge.id, edge);
          rebuildConduits();
          refreshLabels();
          continue;
        }
        if (event.type === "entity_classified") {
          const payload = event.payload as { entity_id?: string; cluster_id?: string };
          const id = payload.entity_id ?? event.persisted_id;
          if (typeof id === "string" && entities.has(id)) {
            const existing = entities.get(id)!;
            entities.set(id, { ...existing, cluster_id: payload.cluster_id });
            syncSlots();
            rebuildConduits();
            refreshLabels();
          }
          continue;
        }
        if (event.type === "cluster_health_changed") refreshLabels();
        void nowMs;
      }
      liveEventsRef.current = deferred.slice(-20);
    };

    const onPointerMove = (ev: PointerEvent) => {
      idleOrbit.noteUserInput(ev.timeStamp);
      setPointer(ev);
      hoveredIdRef.current = hitNodeId();
    };
    const onPointerDown = (ev: PointerEvent) => {
      idleOrbit.noteUserInput(ev.timeStamp);
      setPointer(ev);
      const nodeId = hitNodeId();
      if (nodeId) {
        select(nodeId);
        const target = positionsById.get(nodeId);
        if (target) startCameraFlight(target, 54, ev.timeStamp);
        return;
      }
      const cluster = hitHubCluster();
      if (cluster) {
        selectCluster(cluster);
        startCameraFlight(CLUSTER_CENTROIDS[cluster], 72, ev.timeStamp);
        return;
      }
      resetCamera();
    };
    const onKeyDown = (ev: KeyboardEvent) => {
      idleOrbit.noteUserInput(ev.timeStamp);
      const target = ev.target;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return;
      const key = ev.key.toLowerCase();
      if (key === "escape") {
        ev.preventDefault();
        resetCamera();
      }
      if (shouldResetCameraFromKey(key, paletteOpen) || key === "0") {
        ev.preventDefault();
        resetCamera();
      }
    };
    const onFlyToEntity = (ev: Event) => {
      const id = (ev as CustomEvent<{ id?: string }>).detail?.id;
      if (!id) return;
      const position = findEntityPosition(entities.get(id), positionsById, CLUSTER_CENTROIDS);
      if (!position) return;
      select(id);
      startCameraFlight(position, 54);
    };
    const onPaletteState = (ev: Event) => {
      paletteOpen = Boolean((ev as CustomEvent<{ open?: boolean }>).detail?.open);
    };
    const onTraverseClusters = () => {
      const route: ClusterId[] = ["company_knowledge", "execution_context", "agents"];
      route.forEach((cluster, index) => {
        traversalTimers.push(window.setTimeout(() => startCameraFlight(CLUSTER_CENTROIDS[cluster], 86), index * 850));
      });
    };

    renderer.domElement.addEventListener("pointermove", onPointerMove);
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("wheel", (event) => idleOrbit.noteUserInput(event.timeStamp), { passive: true });
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("axiom:fly-to-entity", onFlyToEntity);
    window.addEventListener("axiom:palette-state", onPaletteState);
    window.addEventListener("axiom:traverse-clusters", onTraverseClusters);

    const fps = new RollingFpsCounter(60);
    let raf = 0;
    let lastFrameMs = 0;
    const tick = (t: number) => {
      const dt = lastFrameMs === 0 ? 16.7 : t - lastFrameMs;
      lastFrameMs = t;
      void dt;
      processLiveEvents(t);
      stars.update(t);
      for (const [index, cluster] of VISUAL_CLUSTER_IDS.entries()) {
        const hub = hubMeshes.get(cluster);
        if (hub) hub.material.emissiveIntensity = hubEmissiveIntensityAt(HUB_EMISSIVE, index, t);
        const core = hubCores[index];
        if (core) core.scale.setScalar(0.9 + Math.sin(t * 0.0015 + index) * 0.05);
        const halo = hubHalos[index];
        if (halo) halo.material.opacity = (cluster === "company_knowledge" || cluster === "execution_context" ? 0.28 : 0.18) + Math.sin(t * 0.0012 + index) * 0.025;
      }
      const selectedId = useBrainStore.getState().selectedId;
      for (let i = 0; i < slots.length; i++) composeNodeTransform(nodeMesh, i, slots[i], selectedId, hoveredIdRef.current, t);
      nodeMesh.instanceMatrix.needsUpdate = true;
      if (selectedId && positionsById.has(selectedId)) {
        selectionRing.visible = true;
        selectionRing.position.copy(positionsById.get(selectedId)!);
        selectionRing.lookAt(camera.position);
      } else {
        selectionRing.visible = false;
      }
      particleFlow.update(t);
      for (const [key, line] of linesByKey) {
        const material = line.material as THREE.LineBasicMaterial;
        material.opacity = hoveredIdRef.current || selectedId ? 0.13 : 0.08;
        void key;
      }
      if (cameraFlight) {
        const progress = Math.min(1, (t - cameraFlight.startedAt) / CAMERA_ANIMATION_MS);
        const eased = easeInOutCubic(progress);
        camera.position.lerpVectors(cameraFlight.fromPosition, cameraFlight.toPosition, eased);
        controls.target.lerpVectors(cameraFlight.fromTarget, cameraFlight.toTarget, eased);
        if (progress >= 1) cameraFlight = null;
      }
      if (!cameraFlight) idleOrbit.update(t);
      controls.update();
      composer.render();
      labelRenderer.render(scene, camera);
      const fpsValue = fps.tick(t);
      if (fpsValue) setFps(fpsValue);
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);

    const onResize = () => {
      const w = el.clientWidth || window.innerWidth;
      const h = el.clientHeight || window.innerHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      composer.setSize(w, h);
      labelRenderer.setSize(w, h);
    };
    window.addEventListener("resize", onResize);

    return () => {
      traversalTimers.forEach((timer) => window.clearTimeout(timer));
      window.cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("axiom:fly-to-entity", onFlyToEntity);
      window.removeEventListener("axiom:palette-state", onPaletteState);
      window.removeEventListener("axiom:traverse-clusters", onTraverseClusters);
      controls.dispose();
      composer.dispose();
      stars.dispose();
      particleFlow.dispose();
      grid.geometry.dispose();
      grid.material.map?.dispose();
      grid.material.dispose();
      haloTexture.dispose();
      hubGeometry.dispose();
      hubMeshes.forEach((mesh) => mesh.material.dispose());
      hubCores.forEach((mesh) => {
        mesh.geometry.dispose();
        (mesh.material as THREE.Material).dispose();
      });
      hubHalos.forEach((sprite) => sprite.material.dispose());
      nodeGeometry.dispose();
      nodeMaterial.dispose();
      intraWeb.geometry.dispose();
      (intraWeb.material as THREE.Material).dispose();
      bracketLines.traverse((obj) => {
        if (obj instanceof THREE.Line) {
          obj.geometry.dispose();
          (obj.material as THREE.Material).dispose();
        }
      });
      interHubLines.traverse((obj) => {
        if (obj instanceof THREE.Line) {
          obj.geometry.dispose();
          (obj.material as THREE.Material).dispose();
        }
      });
      selectionRing.geometry.dispose();
      (selectionRing.material as THREE.Material).dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === el) el.removeChild(renderer.domElement);
      if (labelRenderer.domElement.parentNode === el) el.removeChild(labelRenderer.domElement);
      labelObjects.clear();
      labelDivs.clear();
    };
  }, [sceneReady, select, selectCluster, setFps]);

  return <div ref={containerRef} className="absolute inset-0" aria-hidden="true" />;
}
