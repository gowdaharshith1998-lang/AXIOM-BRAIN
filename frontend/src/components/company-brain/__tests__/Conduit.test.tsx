import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import { Conduit } from "@/components/company-brain/Conduit";

describe("Conduit (spec)", () => {
  it("renders curved quadratic Bezier conduits from clusters to the central hub", () => {
    const { container } = render(
      <svg viewBox="0 0 1700 950">
        <defs>
          <filter id="particle-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="1.8" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <Conduit
          clusterId="people"
          sourceColor="#2788ff"
          hubColor="#2f8dff"
          sourceCentroid={{ x: 510, y: 145 }}
          hubCentroid={{ x: 806, y: 350 }}
          isFocusedMode={false}
          isThisClusterFocused={false}
          particleCount={2}
        />
        <Conduit
          clusterId="systems"
          sourceColor="#65e78f"
          hubColor="#2f8dff"
          sourceCentroid={{ x: 970, y: 520 }}
          hubCentroid={{ x: 806, y: 350 }}
          isFocusedMode={false}
          isThisClusterFocused={false}
          particleCount={2}
        />
      </svg>,
    );
    const conduits = container.querySelectorAll('path[data-role="conduit-path"]');
    expect(conduits.length).toBeGreaterThanOrEqual(2);
    expect(Array.from(conduits).every((p) => (p.getAttribute("d") ?? "").includes("Q"))).toBe(true);
  });

  it("each conduit uses a gradient stroke from cluster-color to hub-color", () => {
    const { container } = render(
      <svg viewBox="0 0 1700 950">
        <defs>
          <filter id="particle-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="1.8" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <Conduit
          clusterId="people"
          sourceColor="#2788ff"
          hubColor="#2f8dff"
          sourceCentroid={{ x: 510, y: 145 }}
          hubCentroid={{ x: 806, y: 350 }}
          isFocusedMode={false}
          isThisClusterFocused={false}
          particleCount={2}
        />
        <Conduit
          clusterId="systems"
          sourceColor="#65e78f"
          hubColor="#2f8dff"
          sourceCentroid={{ x: 970, y: 520 }}
          hubCentroid={{ x: 806, y: 350 }}
          isFocusedMode={false}
          isThisClusterFocused={false}
          particleCount={2}
        />
      </svg>,
    );
    expect(container.querySelectorAll("linearGradient").length).toBeGreaterThanOrEqual(2);
    const conduits = container.querySelectorAll('path[data-role="conduit-path"]');
    expect(Array.from(conduits).every((p) => (p.getAttribute("stroke") ?? "").startsWith("url(#"))).toBe(true);
  });

  it("every conduit hosts ≥ 1 animated particle using <animateMotion>", () => {
    const { container } = render(
      <svg viewBox="0 0 1700 950">
        <defs>
          <filter id="particle-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="1.8" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <Conduit
          clusterId="people"
          sourceColor="#2788ff"
          hubColor="#2f8dff"
          sourceCentroid={{ x: 510, y: 145 }}
          hubCentroid={{ x: 806, y: 350 }}
          isFocusedMode={false}
          isThisClusterFocused={false}
          particleCount={2}
        />
        <Conduit
          clusterId="systems"
          sourceColor="#65e78f"
          hubColor="#2f8dff"
          sourceCentroid={{ x: 970, y: 520 }}
          hubCentroid={{ x: 806, y: 350 }}
          isFocusedMode={false}
          isThisClusterFocused={false}
          particleCount={2}
        />
      </svg>,
    );
    expect(container.querySelectorAll("animateMotion").length).toBeGreaterThanOrEqual(2);
    expect(container.querySelectorAll('circle[data-role="conduit-particle"]').length).toBeGreaterThanOrEqual(2);
  });

  it("in focus mode, non-focused conduits dim to opacity ≤ 0.2", () => {
    const { container } = render(
      <svg viewBox="0 0 1700 950">
        <defs>
          <filter id="particle-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="1.8" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <Conduit
          clusterId="people"
          sourceColor="#2788ff"
          hubColor="#2f8dff"
          sourceCentroid={{ x: 510, y: 145 }}
          hubCentroid={{ x: 806, y: 350 }}
          isFocusedMode
          isThisClusterFocused={false}
          particleCount={2}
        />
        <Conduit
          clusterId="systems"
          sourceColor="#65e78f"
          hubColor="#2f8dff"
          sourceCentroid={{ x: 970, y: 520 }}
          hubCentroid={{ x: 806, y: 350 }}
          isFocusedMode
          isThisClusterFocused
          particleCount={2}
        />
      </svg>,
    );
    const nonFocused = container.querySelectorAll('path[data-role="conduit-path"][data-dimmed="true"]');
    expect(nonFocused.length).toBeGreaterThanOrEqual(1);
    expect(
      Array.from(nonFocused).every((p) => Number(p.getAttribute("opacity") ?? "1") <= 0.2),
    ).toBe(true);
  });
});

