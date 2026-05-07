import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { useEffect, useRef, useState } from "react";

import { arrivalColorForCluster } from "@/components/ArrivalEffect";
import {
  createClusterAuras,
  updateClusterAuras,
} from "@/components/ClusterAura";
import {
  bracketLinePoints,
  clusterLabelAnchor,
  createClusterBracketElement,
  updateClusterBracketElement,
} from "@/components/ClusterBracketLabel";
import { createHexGridPlane } from "@/components/HexGridBackground";
import { easeInOutCubic, RESET_CAMERA_MS, shouldResetCameraFromKey } from "@/lib/camera-reset";
import { flyToEntity } from "@/lib/camera-flyto";
import {
  CLUSTER_CENTROIDS,
  CLUSTER_COLORS,
  CLUSTER_IDS,
  isClusterId,
  type ClusterId,
} from "@/lib/cluster-layout";
import { createEdgeMaterialForClusters } from "@/lib/edge-style";
import { RollingFpsCounter } from "@/lib/fps";
import { FpsGuard } from "@/lib/fps-guard";
import { createHexPrismGeometry, HEX_HEIGHT, HEX_HUB_RADIUS, HEX_NODE_RADIUS } from "@/lib/hex-geometry";
import {
  computeInterHubEdges,
  computeVisibleEntitySlots,
  findEntityPosition,
  MAX_VISIBLE_PER_CLUSTER,
  type InterHubEdge,
  type VisibleEntitySlot,
} from "@/lib/hex-layout";
import { BLOOM_FULL_STRENGTH } from "@/lib/lod";
import { ParticleFlowController } from "@/lib/particle-flow";
import { ParticleEffectSystem } from "@/lib/particles/agent-effects";
import { createNebulaBackground } from "@/lib/particles/nebula-bg";
import { spawnEdgeTrace, spawnEntityArrival } from "@/lib/particles/reactive-spawn";
import { RadialTrafficController } from "@/lib/radial-traffic";
import { hashStringToFloat, hubEmissiveIntensityAt, shimmerScale } from "@/lib/spoke-shimmer";
import { hasWebGPU, preferredRendererKind } from "@/lib/webgpu-detect";
import { BrainSocket, type BrainEvent } from "@/lib/websocket";
import { useBrainStore } from "@/state/brain.store";
import type { Edge, Entity } from "@/state/brain.store";

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as T;
}

const INITIAL_CAMERA_POSITION = new THREE.Vector3(0, 0, 280);
const CAMERA_ANIMATION_MS = RESET_CAMERA_MS;
const NODE_EMISSIVE = 0.7;
const HUB_EMISSIVE = 1.4;
const SELECTED_SCALE = 1.22;
const FLASH_MS = 650;

function compositeImportance(entity: Entity | undefined): number {
  if (!entity) return 0;
  const direct = entity.composite_importance;
  if (typeof direct === "number" && Number.isFinite(direct)) return THREE.MathUtils.clamp(direct, 0, 1);
  const nested = entity.data?.composite_importance;
  return typeof nested === "number" && Number.isFinite(nested) ? THREE.MathUtils.clamp(nested, 0, 1) : 0;
}

function clusterIdFor(entity: Entity | undefined): ClusterId | null {
  return isClusterId(entity?.cluster_id) ? entity.cluster_id : null;
}

function clusterCounts(entities: Iterable<Entity>): Map<ClusterId, number> {
  const counts = new Map<ClusterId, number>();
  for (const cluster of CLUSTER_IDS) counts.set(cluster, 0);
  for (const entity of entities) {
    const cluster = clusterIdFor(entity);
    if (cluster) counts.set(cluster, (counts.get(cluster) ?? 0) + 1);
  }
  return counts;
}

function setInstanceTransform(
  mesh: THREE.InstancedMesh,
  index: number,
  slot: VisibleEntitySlot,
  selectedId: string | null,
  hoveredId: string | null,
  flashUntil: number | undefined,
  now: number,
): void {
  const matrix = new THREE.Matrix4();
  const quat = new THREE.Quaternion();
  const importanceScale = THREE.MathUtils.lerp(0.7, 1.6, compositeImportance(slot.entity));
  const selectedScale = slot.entity.id === selectedId ? SELECTED_SCALE : 1;
  const hoverScale = slot.entity.id === hoveredId ? 1.14 : 1;
  const flashScale = flashUntil && flashUntil > now ? 1 + ((flashUntil - now) / FLASH_MS) * 0.25 : 1;
  const spokeScale = shimmerScale(hashStringToFloat(slot.entity.id), now);
  const scale = new THREE.Vector3(
    importanceScale * selectedScale * hoverScale * flashScale * spokeScale,
    importanceScale * selectedScale * hoverScale * flashScale * spokeScale,
    1,
  );
  matrix.compose(slot.position, quat, scale);
  mesh.setMatrixAt(index, matrix);
}

function buildRadialEdges(slots: VisibleEntitySlot[]): THREE.Group {
  const group = new THREE.Group();
  for (const cluster of CLUSTER_IDS) {
    const clusterSlots = slots.filter((slot) => slot.clusterId === cluster);
    const positions = new Float32Array(clusterSlots.length * 2 * 3);
    const hub = CLUSTER_CENTROIDS[cluster];
    let index = 0;
    for (const slot of clusterSlots) {
      positions[index++] = hub.x;
      positions[index++] = hub.y;
      positions[index++] = hub.z;
      positions[index++] = slot.position.x;
      positions[index++] = slot.position.y;
      positions[index++] = slot.position.z;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const material = new THREE.LineBasicMaterial({
      color: CLUSTER_COLORS[cluster],
      transparent: true,
      opacity: 0.3,
      depthWrite: false,
    });
    group.add(new THREE.LineSegments(geometry, material));
  }
  return group;
}

function buildInterHubEdges(interHubEdges: InterHubEdge[]): THREE.LineSegments {
  const positions = new Float32Array(interHubEdges.length * 2 * 3);
  let index = 0;
  for (const edge of interHubEdges) {
    const source = CLUSTER_CENTROIDS[edge.sourceCluster];
    const target = CLUSTER_CENTROIDS[edge.targetCluster];
    positions[index++] = source.x;
    positions[index++] = source.y;
    positions[index++] = source.z;
    positions[index++] = target.x;
    positions[index++] = target.y;
    positions[index++] = target.z;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  const material = createEdgeMaterialForClusters("billing_payments", "incidents_ops", "#ffffff");
  material.opacity = 0.25;
  const lines = new THREE.LineSegments(geometry, material);
  lines.computeLineDistances();
  return lines;
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

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !sceneReady) return;

    const state = useBrainStore.getState();
    const entities = new Map(state.entities);
    const edges = new Map(state.edges);
    let slots = computeVisibleEntitySlots(entities.values(), CLUSTER_IDS);
    let interHubEdges = computeInterHubEdges(edges.values(), entities);
    const positionsById = new Map(slots.map((slot) => [slot.entity.id, slot.position.clone()]));
    const idByInstanceIndex = slots.map((slot) => slot.entity.id);

    const width = el.clientWidth || window.innerWidth;
    const height = el.clientHeight || window.innerHeight;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#05050a");
    const nebula = createNebulaBackground();
    scene.add(nebula.mesh);
    const grid = createHexGridPlane();
    scene.add(grid);
    const clusterAuras = createClusterAuras();
    for (const aura of clusterAuras) scene.add(aura);

    const camera = new THREE.PerspectiveCamera(60, width / height, 1, 4000);
    camera.position.copy(INITIAL_CAMERA_POSITION);
    const ambient = new THREE.AmbientLight(0xffffff, 0.55);
    scene.add(ambient);
    const keyLight = new THREE.DirectionalLight(0xffffff, 0.9);
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

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.target.set(0, 0, 0);

    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloomPass = new UnrealBloomPass(new THREE.Vector2(width, height), BLOOM_FULL_STRENGTH, 0.4, 0.85);
    composer.addPass(bloomPass);

    const labelRenderer = new CSS2DRenderer();
    labelRenderer.setSize(width, height);
    labelRenderer.domElement.classList.add("axiom-labels");
    labelRenderer.domElement.style.position = "absolute";
    labelRenderer.domElement.style.inset = "0";
    labelRenderer.domElement.style.pointerEvents = "none";
    labelRenderer.domElement.style.userSelect = "none";
    el.appendChild(labelRenderer.domElement);

    const bracketLabelObjects = new Map<ClusterId, CSS2DObject>();
    const bracketLabelDivs = new Map<ClusterId, HTMLDivElement>();
    const initialCounts = clusterCounts(entities.values());
    for (const cluster of CLUSTER_IDS) {
      const hub = CLUSTER_CENTROIDS[cluster];
      const anchor = clusterLabelAnchor(hub);
      const div = createClusterBracketElement(cluster, initialCounts.get(cluster) ?? 0);
      const object = new CSS2DObject(div);
      object.position.copy(anchor);
      scene.add(object);
      bracketLabelObjects.set(cluster, object);
      bracketLabelDivs.set(cluster, div);
    }

    const bracketLines = new THREE.Group();
    for (const cluster of CLUSTER_IDS) {
      const hub = CLUSTER_CENTROIDS[cluster];
      const anchor = clusterLabelAnchor(hub);
      const points = bracketLinePoints(hub, anchor);
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      const material = new THREE.LineBasicMaterial({
        color: CLUSTER_COLORS[cluster],
        transparent: true,
        opacity: 0.65,
        depthWrite: false,
      });
      bracketLines.add(new THREE.Line(geometry, material));
    }
    scene.add(bracketLines);

    const nodeGeometry = createHexPrismGeometry(HEX_NODE_RADIUS, HEX_HEIGHT);
    const nodeMaterial = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      emissive: 0xffffff,
      emissiveIntensity: NODE_EMISSIVE,
      metalness: 0.2,
      roughness: 0.45,
      transparent: true,
      opacity: 0.95,
    });
    const nodeMesh = new THREE.InstancedMesh(
      nodeGeometry,
      nodeMaterial,
      Math.max(CLUSTER_IDS.length * MAX_VISIBLE_PER_CLUSTER, 1),
    );
    nodeMesh.count = slots.length;
    nodeMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    for (let i = 0; i < slots.length; i++) {
      setInstanceTransform(nodeMesh, i, slots[i], null, null, undefined, 0);
      nodeMesh.setColorAt(i, new THREE.Color(CLUSTER_COLORS[slots[i].clusterId]));
    }
    if (nodeMesh.instanceColor) nodeMesh.instanceColor.needsUpdate = true;
    scene.add(nodeMesh);

    const hubGeometry = createHexPrismGeometry(HEX_HUB_RADIUS, HEX_HEIGHT * 1.4);
    const hubMeshes = new Map<ClusterId, THREE.Mesh<THREE.CylinderGeometry, THREE.MeshStandardMaterial>>();
    for (const cluster of CLUSTER_IDS) {
      const color = new THREE.Color(CLUSTER_COLORS[cluster]);
      const mesh = new THREE.Mesh(
        hubGeometry,
        new THREE.MeshStandardMaterial({
          color,
          emissive: color,
          emissiveIntensity: HUB_EMISSIVE,
          metalness: 0.25,
          roughness: 0.35,
        }),
      );
      mesh.position.copy(CLUSTER_CENTROIDS[cluster]);
      mesh.scale.setScalar(1.08);
      mesh.userData = { cluster };
      hubMeshes.set(cluster, mesh);
      scene.add(mesh);
    }

    let radialEdges = buildRadialEdges(slots);
    scene.add(radialEdges);
    let interHubLines = buildInterHubEdges(interHubEdges);
    scene.add(interHubLines);

    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(HEX_NODE_RADIUS * 2.1, 0.055, 6, 48),
      new THREE.MeshBasicMaterial({
        color: "#ffffff",
        transparent: true,
        opacity: 0.8,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    ring.visible = false;
    scene.add(ring);

    const particleSystem = new ParticleEffectSystem();
    scene.add(particleSystem.points);
    const particleFlow = new ParticleFlowController(interHubEdges);
    scene.add(particleFlow.points);
    const radialTraffic = new RadialTrafficController(slots);
    scene.add(radialTraffic.points);
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const hoveredIdRef = { current: null as string | null };
    const flashByNode = new Map<string, number>();
    const flashByEdge = new Map<string, number>();
    let paletteOpen = false;
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

    const syncSlotIndexes = () => {
      positionsById.clear();
      idByInstanceIndex.length = 0;
      nodeMesh.count = slots.length;
      slots.forEach((slot, index) => {
        positionsById.set(slot.entity.id, slot.position.clone());
        idByInstanceIndex.push(slot.entity.id);
        nodeMesh.setColorAt(index, new THREE.Color(CLUSTER_COLORS[slot.clusterId]));
      });
      if (nodeMesh.instanceColor) nodeMesh.instanceColor.needsUpdate = true;
      radialTraffic.setSlots(slots, performance.now());
    };

    const refreshInstanceTransforms = (now: number) => {
      const selectedId = useBrainStore.getState().selectedId;
      for (let i = 0; i < slots.length; i++) {
        setInstanceTransform(
          nodeMesh,
          i,
          slots[i],
          selectedId,
          hoveredIdRef.current,
          flashByNode.get(slots[i].entity.id),
          now,
        );
      }
      nodeMesh.instanceMatrix.needsUpdate = true;
    };

    const updateSelectionRing = () => {
      const selectedId = useBrainStore.getState().selectedId;
      if (!selectedId) {
        ring.visible = false;
        return;
      }
      const selected = entities.get(selectedId);
      const position = findEntityPosition(selected, positionsById);
      if (!position) {
        ring.visible = false;
        return;
      }
      ring.position.copy(position);
      ring.lookAt(camera.position);
      const color = clusterIdFor(selected) ? CLUSTER_COLORS[clusterIdFor(selected)!] : "#ffffff";
      ring.material.color.set(color);
      ring.visible = true;
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
    };

    const resetCamera = () => {
      startCameraFlight(INITIAL_CAMERA_POSITION.clone(), new THREE.Vector3(0, 0, 0));
    };

    const setPointer = (ev: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
    };

    const hitNodeId = (): string | null => {
      raycaster.setFromCamera(pointer, camera);
      const hits = raycaster.intersectObject(nodeMesh, false);
      const instanceId = hits[0]?.instanceId;
      return typeof instanceId === "number" ? (idByInstanceIndex[instanceId] ?? null) : null;
    };

    const onPointerMove = (ev: PointerEvent) => {
      setPointer(ev);
      hoveredIdRef.current = hitNodeId();
    };

    const onPointerDown = (ev: PointerEvent) => {
      setPointer(ev);
      const id = hitNodeId();
      if (!id) {
        select(null);
        return;
      }
      select(id);
      const target = positionsById.get(id);
      if (target) focusTargetRef.current = target.clone();
      flashByNode.set(id, ev.timeStamp + 450);
    };

    const onKeyDown = (ev: KeyboardEvent) => {
      const target = ev.target;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) {
        return;
      }
      const key = ev.key.toLowerCase();
      if (key === "escape") {
        ev.preventDefault();
        select(null);
      }
      if (shouldResetCameraFromKey(key, paletteOpen) || key === "0") {
        ev.preventDefault();
        resetCamera();
      }
    };

    const onFlyToEntity = (ev: Event) => {
      const id = (ev as CustomEvent<{ id?: string }>).detail?.id;
      if (!id) return;
      const entity = entities.get(id);
      const position = findEntityPosition(entity, positionsById);
      if (!position) return;
      select(id);
      focusTargetRef.current = null;
      flyToEntity(camera, controls, position, 1200);
      flashByNode.set(id, performance.now() + 450);
    };

    const onHudResetView = () => resetCamera();
    const onPaletteState = (ev: Event) => {
      paletteOpen = Boolean((ev as CustomEvent<{ open?: boolean }>).detail?.open);
    };

    const rebuildEdges = () => {
      scene.remove(radialEdges);
      radialEdges.traverse((obj) => {
        if (obj instanceof THREE.LineSegments) {
          obj.geometry.dispose();
          (obj.material as THREE.Material).dispose();
        }
      });
      radialEdges = buildRadialEdges(slots);
      scene.add(radialEdges);

      scene.remove(interHubLines);
      interHubLines.geometry.dispose();
      (interHubLines.material as THREE.Material).dispose();
      interHubEdges = computeInterHubEdges(edges.values(), entities);
      interHubLines = buildInterHubEdges(interHubEdges);
      scene.add(interHubLines);
      particleFlow.setEdges(interHubEdges, performance.now());
      radialTraffic.setSlots(slots, performance.now());
    };

    const refreshClusterLabels = () => {
      const counts = clusterCounts(entities.values());
      for (const cluster of CLUSTER_IDS) {
        const div = bracketLabelDivs.get(cluster);
        if (div) updateClusterBracketElement(div, cluster, counts.get(cluster) ?? 0);
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
          entities.set(entity.id, entity);
          const cluster = clusterIdFor(entity);
          const clusterVisible = slots.filter((slot) => slot.clusterId === cluster).length;
          if (cluster && clusterVisible < 26) {
            slots = computeVisibleEntitySlots(entities.values(), CLUSTER_IDS);
            syncSlotIndexes();
            rebuildEdges();
          }
          const position = findEntityPosition(entity, positionsById) ?? new THREE.Vector3();
          const clusterColor = arrivalColorForCluster(entity.cluster_id);
          spawnEntityArrival(particleSystem, position, new THREE.Color(clusterColor));
          particleSystem.ingestStream(position, clusterColor);
          flashByNode.set(entity.id, nowMs + FLASH_MS);
          refreshClusterLabels();
          continue;
        }

        if ((event.type === "edge_added" || event.type === "entity_edge_created") && event.persisted_id) {
          const payload = event.payload as Partial<Omit<Edge, "id">> & {
            relation_type?: string;
            relationship?: string;
          };
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
          const previousPairCount = interHubEdges.length;
          rebuildEdges();
          const src = findEntityPosition(entities.get(edge.source_id), positionsById);
          const tgt = findEntityPosition(entities.get(edge.target_id), positionsById);
          if (src && tgt) {
            spawnEdgeTrace(particleSystem, src, tgt, "#ffffff");
            flashByEdge.set(edge.id, nowMs + FLASH_MS);
          }
          if (event.type === "entity_edge_created" || interHubEdges.length > previousPairCount) {
            const sourceCluster = clusterIdFor(entities.get(edge.source_id));
            const targetCluster = clusterIdFor(entities.get(edge.target_id));
            if (sourceCluster && targetCluster && sourceCluster !== targetCluster) {
              const pair = interHubEdges.find(
                (item) =>
                  (item.sourceCluster === sourceCluster && item.targetCluster === targetCluster) ||
                  (item.sourceCluster === targetCluster && item.targetCluster === sourceCluster),
              );
              if (pair) particleFlow.burst(pair, nowMs);
            }
          }
          continue;
        }

        if (event.type === "entity_classified") {
          const payload = event.payload as { entity_id?: string; cluster_id?: string };
          const entityId = payload.entity_id ?? event.persisted_id;
          if (typeof entityId !== "string" || !isClusterId(payload.cluster_id)) continue;
          const existing = entities.get(entityId);
          if (!existing) continue;
          entities.set(entityId, { ...existing, cluster_id: payload.cluster_id });
          slots = computeVisibleEntitySlots(entities.values(), CLUSTER_IDS);
          syncSlotIndexes();
          rebuildEdges();
          refreshClusterLabels();
          continue;
        }

        if (event.type === "entity_modified") {
          const id = event.persisted_id ?? event.source_id;
          if (typeof id !== "string") continue;
          flashByNode.set(id, nowMs + 500);
        }
      }
      liveEventsRef.current = deferred.slice(-20);
    };

    renderer.domElement.addEventListener("pointermove", onPointerMove);
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("axiom:reset-view", onHudResetView);
    window.addEventListener("axiom:fly-to-entity", onFlyToEntity);
    window.addEventListener("axiom:palette-state", onPaletteState);

    const fps = new RollingFpsCounter(60);
    const fpsGuard = new FpsGuard();
    let raf = 0;
    let lastFrameMs = 0;

    const tick = (t: number) => {
      const dtMs = lastFrameMs === 0 ? 16.7 : t - lastFrameMs;
      lastFrameMs = t;
      void dtMs;
      processLiveEvents(t);
      nebula.update(t);
      nebula.mesh.rotation.z += 0.00012;
      nebula.mesh.rotation.y += 0.00007;
      updateClusterAuras(clusterAuras, t);
      for (const [index, cluster] of CLUSTER_IDS.entries()) {
        const hub = hubMeshes.get(cluster);
        if (hub) hub.material.emissiveIntensity = hubEmissiveIntensityAt(HUB_EMISSIVE, index, t);
      }
      refreshInstanceTransforms(t);
      updateSelectionRing();
      particleSystem.setParticleMultiplier(fpsGuard.particleMultiplier());
      particleSystem.update(t);
      particleFlow.update(t);
      radialTraffic.update(t);
      const selectedId = useBrainStore.getState().selectedId;
      if (selectedId) {
        const target = findEntityPosition(entities.get(selectedId), positionsById);
        if (target) {
          const desired = target.clone().add(new THREE.Vector3(0, 18, 55));
          if (focusTargetRef.current) {
            camera.position.lerp(desired, 0.08);
            controls.target.lerp(target, 0.12);
            if (camera.position.distanceTo(desired) < 0.1) focusTargetRef.current = null;
          }
        }
      }
      if (cameraFlight) {
        const progress = Math.min(1, (t - cameraFlight.startedAt) / cameraFlight.durationMs);
        const eased = easeInOutCubic(progress);
        camera.position.lerpVectors(cameraFlight.fromPosition, cameraFlight.toPosition, eased);
        controls.target.lerpVectors(cameraFlight.fromTarget, cameraFlight.toTarget, eased);
        if (progress >= 1) cameraFlight = null;
      }
      ring.lookAt(camera.position);
      controls.update();
      composer.render();
      labelRenderer.render(scene, camera);
      const value = fps.tick(t);
      if (value) {
        setFps(value);
        fpsGuard.sample(value, t);
      }
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
      window.removeEventListener("resize", onResize);
      window.cancelAnimationFrame(raf);
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("axiom:reset-view", onHudResetView);
      window.removeEventListener("axiom:fly-to-entity", onFlyToEntity);
      window.removeEventListener("axiom:palette-state", onPaletteState);
      controls.dispose();
      composer.dispose();
      nebula.dispose();
      particleSystem.dispose();
      particleFlow.dispose();
      radialTraffic.dispose();
      renderer.dispose();
      grid.geometry.dispose();
      grid.material.map?.dispose();
      grid.material.dispose();
      nodeGeometry.dispose();
      nodeMaterial.dispose();
      hubGeometry.dispose();
      hubMeshes.forEach((mesh) => mesh.material.dispose());
      clusterAuras.forEach((aura) => {
        scene.remove(aura);
        aura.geometry.dispose();
        aura.material.dispose();
      });
      bracketLabelObjects.clear();
      bracketLabelDivs.clear();
      bracketLines.traverse((obj) => {
        if (obj instanceof THREE.Line) {
          obj.geometry.dispose();
          (obj.material as THREE.Material).dispose();
        }
      });
      radialEdges.traverse((obj) => {
        if (obj instanceof THREE.LineSegments) {
          obj.geometry.dispose();
          (obj.material as THREE.Material).dispose();
        }
      });
      interHubLines.geometry.dispose();
      (interHubLines.material as THREE.Material).dispose();
      ring.geometry.dispose();
      ring.material.dispose();
      if (renderer.domElement.parentNode === el) el.removeChild(renderer.domElement);
      if (labelRenderer.domElement.parentNode === el) el.removeChild(labelRenderer.domElement);
    };
  }, [sceneReady, select, setFps]);

  return <div ref={containerRef} className="absolute inset-0" aria-hidden="true" />;
}
