import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";

import { HUB_CENTROID_FRAC, HUB_COLOR } from "@/lib/cluster-layout";
import { HubNode } from "@/components/company-brain/HubNode";

const VIEWBOX = { width: 1700, height: 950 };

function Harness() {
  return (
    <svg viewBox={`0 0 ${VIEWBOX.width} ${VIEWBOX.height}`} role="img" aria-label="Company Brain hub node">
      <defs>
        <radialGradient id="hub-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.96" />
          <stop offset="36%" stopColor={HUB_COLOR} stopOpacity="0.8" />
          <stop offset="100%" stopColor="#06152f" stopOpacity="0" />
        </radialGradient>
      </defs>
      <HubNode
        hubX={HUB_CENTROID_FRAC.x * VIEWBOX.width}
        hubY={HUB_CENTROID_FRAC.y * VIEWBOX.height}
        hubColor={HUB_COLOR}
      />
    </svg>
  );
}

function parseTranslate(transform: string): { x: number; y: number } | null {
  const match = /translate\(\s*([-\d.]+)[ ,]([-\d.]+)\s*\)/.exec(transform);
  if (!match) return null;
  return { x: Number(match[1]), y: Number(match[2]) };
}

describe("HubNode (spec R4) structure", () => {
  it("renders the hub <g> at the canonical hub centroid (0.474×1700, 0.368×950 ±0.01)", () => {
    const { container } = render(<Harness />);
    const g = container.querySelector('[data-role="hub"]');
    expect(g).toBeTruthy();
    const parsed = parseTranslate(g?.getAttribute("transform") ?? "");
    expect(parsed).toBeTruthy();
    const xFrac = (parsed?.x ?? 0) / VIEWBOX.width;
    const yFrac = (parsed?.y ?? 0) / VIEWBOX.height;
    expect(Math.abs(xFrac - HUB_CENTROID_FRAC.x)).toBeLessThan(0.01);
    expect(Math.abs(yFrac - HUB_CENTROID_FRAC.y)).toBeLessThan(0.01);
  });

  it("hub glyph is a hexagonal polygon (6 points), not a circle or rect", () => {
    const { container } = render(<Harness />);
    const glyph = container.querySelector('[data-role="hub-glyph"]');
    expect(glyph).toBeTruthy();
    expect(glyph?.tagName.toLowerCase()).toBe("polygon");
    const points = (glyph?.getAttribute("points") ?? "").trim().split(/\s+/).filter(Boolean);
    expect(points.length).toBe(6);
  });

  it('renders AXIOM wordmark, COMPANY BRAIN subtitle, and "Knowledge. Connected. Executable." tagline', () => {
    const { container } = render(<Harness />);
    expect(container.querySelector('[data-role="hub-wordmark"]')?.textContent).toBe("AXIOM");
    expect(container.querySelector('[data-role="hub-subtitle"]')?.textContent).toBe("COMPANY BRAIN");
    expect(container.querySelector('[data-role="hub-tagline"]')?.textContent).toBe("Knowledge. Connected. Executable.");
  });

  it("hub ring-pulse element is present with the pulse class in normal motion mode", () => {
    const matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() });
    // @ts-expect-error test shim
    window.matchMedia = matchMedia;
    const { container } = render(<Harness />);
    const ring = container.querySelector('[data-role="hub-ring-pulse"]');
    expect(ring).toBeTruthy();
    expect(ring?.classList.contains("hub-ring-pulse")).toBe(true);
  });

  it("prefers-reduced-motion disables the hub ring-pulse class", () => {
    const matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() });
    // @ts-expect-error test shim
    window.matchMedia = matchMedia;
    const { container } = render(<Harness />);
    const ring = container.querySelector('[data-role="hub-ring-pulse"]');
    expect(ring).toBeTruthy();
    expect(ring?.classList.contains("hub-ring-pulse")).toBe(false);
  });

  it("hub-glyph stroke matches the hub-color token (cyan-blue)", () => {
    const { container } = render(<Harness />);
    const glyph = container.querySelector('[data-role="hub-glyph"]');
    expect(glyph).toBeTruthy();
    expect(glyph?.getAttribute("stroke")).toBe(HUB_COLOR);
  });
});

