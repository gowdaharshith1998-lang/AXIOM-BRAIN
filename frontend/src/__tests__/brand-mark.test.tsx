import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BrandMark } from "@/components/BrandMark";

describe("BrandMark", () => {
  it("renders the AXIOM mark", () => {
    render(<BrandMark />);
    expect(screen.getByText("AXIOM")).toBeInTheDocument();
  });

  it("is centered at the top of the viewport", () => {
    const { container } = render(<BrandMark />);
    expect(container.firstElementChild?.className).toContain("left-1/2");
    expect(container.firstElementChild?.className).toContain("-translate-x-1/2");
  });
});
