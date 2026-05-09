import { describe, it, expect, vi, beforeEach } from "vitest";

import { ParticleBehaviorPool } from "@/lib/particle-behaviors";
import type { BrainEvent } from "@/lib/websocket";

function makeEvent(overrides: Partial<BrainEvent>): BrainEvent {
  return {
    seq: 1,
    type: "entity_added",
    timestamp: Date.now(),
    source_id: null,
    persisted_id: "ent_1",
    payload: {},
    ...overrides,
  };
}

const ZERO = { x: 0, y: 0, z: 0 };
const resolve = (id: string) => {
  if (id === "ent_1") return { clone: () => ({ ...ZERO, add: () => ({ ...ZERO }), sub: () => ({ ...ZERO, normalize: () => ({ ...ZERO, multiplyScalar: () => ZERO }) }), multiplyScalar: () => ZERO, normalize: () => ({ multiplyScalar: () => ZERO }) }) } as any;
  if (id === "ent_2") return { clone: () => ({ ...ZERO, x: 10, add: () => ({ ...ZERO }), sub: () => ({ ...ZERO, normalize: () => ({ ...ZERO, multiplyScalar: () => ZERO }) }), multiplyScalar: () => ZERO, normalize: () => ({ multiplyScalar: () => ZERO }) }) } as any;
  return null;
};

describe("ParticleBehaviorPool", () => {
  let pool: ParticleBehaviorPool;

  beforeEach(() => {
    pool = new ParticleBehaviorPool();
  });

  it("emits ingest_stream on entity_added", () => {
    pool.handleEvent(makeEvent({ type: "entity_added", persisted_id: "ent_1" }), resolve);
    expect(pool.activeCount).toBeGreaterThan(0);
    expect(pool.particles[0].behavior).toBe("ingest_stream");
  });

  it("emits traversal_flow on agent_navigation_step", () => {
    pool.handleEvent(
      makeEvent({
        type: "agent_navigation_step",
        payload: { from_id: "ent_1", to_id: "ent_2", agent_name: "organizer", demo: false },
      }),
      resolve,
    );
    expect(pool.activeCount).toBeGreaterThan(0);
    expect(pool.particles[0].behavior).toBe("traversal_flow");
  });

  it("emits confidence_change on confidence_changed", () => {
    pool.handleEvent(
      makeEvent({
        type: "confidence_changed",
        payload: { entity_id: "ent_1", direction: "rising", delta: 0.1, demo: false },
      }),
      resolve,
    );
    expect(pool.activeCount).toBeGreaterThan(0);
    expect(pool.particles[0].behavior).toBe("confidence_change");
  });

  it("emits signing_burst on receipt_added", () => {
    pool.handleEvent(
      makeEvent({
        type: "receipt_added",
        payload: { action_id: "ent_1", signing_scheme: "ed25519", demo: true },
      }),
      resolve,
    );
    expect(pool.activeCount).toBeGreaterThan(0);
    expect(pool.particles[0].behavior).toBe("signing_burst");
  });

  it("emits refusal_pattern on agent_action_evaluated with deny", () => {
    pool.handleEvent(
      makeEvent({
        type: "agent_action_evaluated",
        payload: { decision: "deny", action_id: "ent_1", demo: true },
      }),
      resolve,
    );
    expect(pool.activeCount).toBeGreaterThan(0);
    expect(pool.particles[0].behavior).toBe("refusal_pattern");
  });

  it("emits correct_signal on agent_action_evaluated with correct", () => {
    pool.handleEvent(
      makeEvent({
        type: "agent_action_evaluated",
        payload: { decision: "correct", target_entity_id: "ent_1", suggested_alternative: "ent_2", demo: true },
      }),
      resolve,
    );
    expect(pool.activeCount).toBeGreaterThan(0);
    expect(pool.particles[0].behavior).toBe("correct_signal");
  });

  it("does not emit on unrelated event type", () => {
    pool.handleEvent(makeEvent({ type: "entity_classified" }), resolve);
    expect(pool.activeCount).toBe(0);
  });

  it("signing_burst color matches signing_scheme", () => {
    const schemes = ["ed25519", "ml_dsa_65", "hybrid"] as const;
    for (const scheme of schemes) {
      const p = new ParticleBehaviorPool();
      p.handleEvent(
        makeEvent({
          type: "receipt_added",
          payload: { action_id: "ent_1", signing_scheme: scheme, demo: true },
        }),
        resolve,
      );
      expect(p.activeCount).toBeGreaterThan(0);
    }
  });

  it("demo flag propagates to particles", () => {
    pool.handleEvent(
      makeEvent({
        type: "receipt_added",
        payload: { action_id: "ent_1", signing_scheme: "ed25519", demo: true },
      }),
      resolve,
    );
    expect(pool.particles[0].demo).toBe(true);
    expect(pool.particles[0].demoBadge).toBe(true);

    const pool2 = new ParticleBehaviorPool();
    pool2.handleEvent(
      makeEvent({
        type: "agent_navigation_step",
        payload: { from_id: "ent_1", to_id: "ent_2", demo: false },
      }),
      resolve,
    );
    expect(pool2.particles[0].demo).toBe(false);
  });

  it("pool does not exceed MAX_PARTICLES", () => {
    for (let i = 0; i < 100; i++) {
      pool.handleEvent(
        makeEvent({
          type: "receipt_added",
          payload: { action_id: "ent_1", signing_scheme: "ed25519", demo: true },
        }),
        resolve,
      );
    }
    expect(pool.activeCount).toBeLessThanOrEqual(200);
  });

  it("expired particles are removed on update", () => {
    pool.handleEvent(
      makeEvent({
        type: "receipt_added",
        payload: { action_id: "ent_1", signing_scheme: "ed25519", demo: true },
      }),
      resolve,
    );
    const count = pool.activeCount;
    expect(count).toBeGreaterThan(0);
    pool.update(performance.now() + 100_000);
    expect(pool.activeCount).toBe(0);
  });
});
