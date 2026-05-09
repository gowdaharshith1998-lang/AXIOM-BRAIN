import * as THREE from "three";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  bracketLinePoints,
  clusterLabelAnchor,
  clusterLabelText,
  ClusterBracketLabel,
  createClusterBracketElement,
  updateClusterBracketElement,
} from "@/components/ClusterBracketLabel";
import { CLUSTER_CENTROIDS } from "@/lib/cluster-layout";

describe("ClusterBracketLabel", () => {
  it("renders the cluster label without metadata", () => {
    render(<ClusterBracketLabel cluster="company_knowledge" count={961} />);
    expect(screen.getByText("COMPANY KNOWLEDGE")).toBeInTheDocument();
    expect(screen.queryByText(/entities/i)).not.toBeInTheDocument();
  });

  it("colors labels by cluster", () => {
    const div = createClusterBracketElement("execution_context", 4);
    expect(div.style.color).toBe("rgb(43, 127, 255)");
  });

  it("positions labels outside the constellation", () => {
    const hub = CLUSTER_CENTROIDS.people_teams;
    const anchor = clusterLabelAnchor(hub);
    expect(anchor.distanceTo(hub)).toBeGreaterThan(10);
  });

  it("computes bracket endpoints from label toward hub", () => {
    const hub = new THREE.Vector3(90, 0, 0);
    const anchor = clusterLabelAnchor(hub);
    const [start, elbow, end] = bracketLinePoints(hub, anchor);
    expect(start).toEqual(anchor);
    expect(end).toEqual(hub);
    expect(elbow.y).toBe(anchor.y);
  });

  it("formats labels in uppercase", () => {
    expect(clusterLabelText("customers")).toBe("CUSTOMERS");
  });

  it("omits count and relationship metadata to match the reference labels", () => {
    const div = createClusterBracketElement("billing", 4, {
      entities: 412,
      relationships: 24800,
    });
    expect(div.textContent).toBe("BILLING");
  });

  it("updates the label name only", () => {
    const div = createClusterBracketElement("billing", 4, { relationships: 1 });
    updateClusterBracketElement(div, "billing", 4, { relationships: 9 });
    expect(div.textContent).toBe("BILLING");
  });
});
