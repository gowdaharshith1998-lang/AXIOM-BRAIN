import { describe, it, expect } from "vitest";
import { compile, decompile } from "../compile";

const REFUND_YAML = `name: handle_refund_request
description: How our company processes refund requests
version: 1
when_triggered_by:
  - intent: refund
    source: [slack, gmail, linear]
steps:
  - id: check_amount
    type: if_then
    condition: trigger.payload.amount > 500
    then:
      - id: require_vp_approval
        type: require_approval
        role: vp_support
        timeout_seconds: 1800
  - id: fetch_customer
    type: fetch_entity
    query: "customer:{trigger.payload.customer_id}"
    bind_to: customer
  - id: log_decision
    type: log_decision
    cluster: billing
    note: "Refund {customer.name}: ${"$"}{trigger.payload.amount}"
`;

describe("compile/decompile", () => {
  it("roundtrips the refund example", () => {
    const doc = decompile(REFUND_YAML);
    expect(doc.name).toBe("handle_refund_request");
    expect(doc.steps).toHaveLength(3);
    expect(doc.steps[0].type).toBe("if_then");
    expect(
      doc.steps[0].type === "if_then" && doc.steps[0].then[0].type,
    ).toBe("require_approval");
    expect(doc.steps[1].type).toBe("fetch_entity");
    expect(doc.steps[2].type).toBe("log_decision");
  });

  it("compile output is re-parseable by decompile", () => {
    const doc = decompile(REFUND_YAML);
    const yamlOut = compile(doc);
    const doc2 = decompile(yamlOut);
    expect(doc2.name).toBe(doc.name);
    expect(doc2.steps).toHaveLength(doc.steps.length);
  });

  it("handles empty steps gracefully", () => {
    const minYaml = `name: empty
description: nothing yet
version: 1
when_triggered_by:
  - intent: refund
steps:
`;
    const doc = decompile(minYaml);
    expect(doc.steps).toHaveLength(0);
    const out = compile(doc);
    expect(out).toContain("steps:");
  });
});
