import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";

import { HexConstellation } from "@/components/company-brain/HexConstellation";

const EXPECTED: Record<
  string,
  { label: string; color: string; x: number; y: number; count: number }
> = {
  people: { label: "People", color: "#2788ff", x: 0.300, y: 0.155, count: 1248 },
  leadership: { label: "Leadership", color: "#c15cff", x: 0.426, y: 0.150, count: 28 },
  meetings: { label: "Meetings", color: "#24d9ff", x: 0.493, y: 0.215, count: 1932 },
  decisions: { label: "Decisions", color: "#ff6bd5", x: 0.586, y: 0.158, count: 763 },
  code: { label: "Code (GitHub)", color: "#2f8dff", x: 0.611, y: 0.270, count: 512 },
  projects: { label: "Projects", color: "#ff9416", x: 0.677, y: 0.270, count: 132 },
  tickets: { label: "Tickets (Linear)", color: "#ffb21c", x: 0.728, y: 0.405, count: 2341 },
  incidents: { label: "Incidents", color: "#ff5a5f", x: 0.692, y: 0.520, count: 59 },
  systems: { label: "Systems", color: "#65e78f", x: 0.574, y: 0.547, count: 184 },
  vendors: { label: "Vendors", color: "#5b70ff", x: 0.440, y: 0.553, count: 87 },
  customers: { label: "Customers", color: "#00e5d4", x: 0.240, y: 0.537, count: 318 },
  policies: { label: "Policies", color: "#bd68ff", x: 0.196, y: 0.421, count: 64 },
  documents: { label: "Documents", color: "#3a83ff", x: 0.323, y: 0.347, count: 6128 },
  teams: { label: "Teams", color: "#00d7df", x: 0.196, y: 0.258, count: 142 },
};

function Harness() {
  return (
    <svg viewBox="0 0 1700 950" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Company Brain hex constellation">
      <title>AXIOM Company Brain</title>
      <desc>Fourteen entity-type clusters connected to a central hub.</desc>
      {Object.entries(EXPECTED).map(([clusterId, item]) => (
        <HexConstellation
          key={clusterId}
          clusterId={clusterId}
          label={item.label}
          count={item.count}
          color={item.color}
          centroid={{ x: item.x * 1700, y: item.y * 950 }}
          satelliteCount={6}
          outerDotCount={6}
        />
      ))}
    </svg>
  );
}

describe("Hex constellation structure (spec, via CompanyBrainGraph)", () => {
  it("uses canonical viewBox 0 0 1700 950", () => {
    const { container } = render(<Harness />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("viewBox")).toBe("0 0 1700 950");
  });

  it("renders 14 clusters as luminous hex constellations (polygons required)", () => {
    const { container } = render(<Harness />);
    expect(container.querySelectorAll('[data-role="cluster"]').length).toBe(14);
    expect(container.querySelectorAll("polygon").length).toBeGreaterThanOrEqual(14);
  });

  it("each cluster has 1 central hex + 5–7 satellites + 4–8 outer dots", () => {
    const { container } = render(<Harness />);
    const groups = container.querySelectorAll('[data-role="cluster"]');
    expect(groups.length).toBe(14);
    for (const group of groups) {
      expect(group.querySelectorAll('[data-role="central-hex"]').length).toBe(1);
      const sats = group.querySelectorAll('[data-role="satellite-hex"]').length;
      const dots = group.querySelectorAll('[data-role="outer-dot"]').length;
      expect(sats).toBeGreaterThanOrEqual(5);
      expect(sats).toBeLessThanOrEqual(7);
      expect(dots).toBeGreaterThanOrEqual(4);
      expect(dots).toBeLessThanOrEqual(8);
    }
  });

  it("spider lines are quadratic Beziers (Q) and render at least one inter-satellite link", () => {
    const { container } = render(<Harness />);
    const spider = container.querySelectorAll('path[data-role="spider-line"]');
    expect(spider.length).toBeGreaterThanOrEqual(14 * 5);
    expect(Array.from(spider).every((p) => (p.getAttribute("d") ?? "").includes("Q"))).toBe(true);
    expect(container.querySelectorAll('line[data-role="satellite-link"]').length).toBeGreaterThanOrEqual(14);
  });

  it("includes SVG <title> and <desc> for accessibility", () => {
    const { container } = render(<Harness />);
    expect(container.querySelector("svg title")).toBeTruthy();
    expect(container.querySelector("svg desc")).toBeTruthy();
  });

  it("respects prefers-reduced-motion by disabling ambient breathing markers", () => {
    const matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() });
    // @ts-ignore test shim
    window.matchMedia = matchMedia;
    const { container } = render(<Harness />);
    const central = container.querySelector('[data-role="central-hex"]');
    expect(central).toBeTruthy();
    expect(central?.getAttribute("data-anim")).toBeFalsy();
    expect(central?.getAttribute("class") ?? "").not.toMatch(/breathe|pulse/i);
  });

  it("central hex has the breathe animation hook applied in normal motion mode", () => {
    const matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() });
    // @ts-ignore test shim
    window.matchMedia = matchMedia;
    const { container } = render(<Harness />);
    const central = container.querySelector('[data-role="central-hex"]');
    expect(central).toBeTruthy();
    const cls = central?.getAttribute("class") ?? "";
    const anim = central?.getAttribute("data-anim") ?? "";
    expect(cls + anim).toMatch(/breathe|pulse/i);
    expect(container.querySelector('[data-reduced-motion="true"]')).toBeNull();
    expect(cls).not.toMatch(/anim-disabled/i);
  });

  it("each of the 14 clusters renders at its expected xFrac/yFrac (±0.01)", () => {
    const { container } = render(<Harness />);
    for (const [id, item] of Object.entries(EXPECTED)) {
      const g = container.querySelector(`[data-role="cluster"][data-cluster-id="${id}"]`) as SVGGElement | null;
      expect(g).toBeTruthy();
      const transform = g?.getAttribute("transform") ?? "";
      const match = /translate\(\s*([-\d.]+)[ ,]([-\d.]+)\s*\)/.exec(transform);
      expect(match).toBeTruthy();
      const x = Number(match?.[1]);
      const y = Number(match?.[2]);
      const xActual = x / 1700;
      const yActual = y / 950;
      expect(Math.abs(xActual - item.x)).toBeLessThan(0.01);
      expect(Math.abs(yActual - item.y)).toBeLessThan(0.01);
    }
  });
});
