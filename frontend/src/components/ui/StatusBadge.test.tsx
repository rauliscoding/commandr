import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it.each(["ok", "warn", "fail", "unknown", "info"] as const)(
    "renders the %s state as visible words with a decorative icon",
    (status) => {
      const { container } = render(<StatusBadge status={status} label={`State ${status}`} />);
      expect(screen.getByText(`State ${status}`)).toBeVisible();
      expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
    },
  );
});
