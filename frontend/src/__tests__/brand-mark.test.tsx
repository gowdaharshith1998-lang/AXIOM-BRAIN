import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { BrandMark } from "@/components/BrandMark";

describe("BrandMark", () => {
  afterEach(cleanup);
  it("renders the AXIOM mark", () => {
    render(<BrandMark />);
    expect(screen.getByText("AXIOM")).toBeInTheDocument();
  });

  it("renders the company-brain tagline", () => {
    render(<BrandMark />);
    expect(screen.getAllByText("Your company, brought to life").length).toBeGreaterThanOrEqual(1);
  });
});
