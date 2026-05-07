import * as THREE from "three";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  bracketLinePoints,
  clusterLabelAnchor,
  clusterLabelText,
  ClusterBracketLabel,
  createClusterBracketElement,
} from "@/components/ClusterBracketLabel";
import { CLUSTER_CENTROIDS } from "@/lib/cluster-layout";

describe("ClusterBracketLabel", () => {
  it("renders the cluster label and count", () => {
    render(<ClusterBracketLabel cluster="billing_payments" count={961} />);
    expect(screen.getByText("BILLING & PAYMENTS")).toBeInTheDocument();
    expect(screen.getByText("961")).toBeInTheDocument();
  });

  it("colors labels by cluster", () => {
    const div = createClusterBracketElement("incidents_ops", 4);
    expect(div.style.color).toBe("rgb(239, 68, 68)");
  });

  it("positions labels outside the constellation", () => {
    const hub = CLUSTER_CENTROIDS.people_teams;
    const anchor = clusterLabelAnchor(hub);
    expect(anchor.distanceTo(hub)).toBeGreaterThan(55);
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
    expect(clusterLabelText("customer_support")).toBe("CUSTOMER SUPPORT");
  });
});
