import { render, screen } from "@testing-library/react";
import { Button } from "@heroui/react";

describe("HeroUI platform smoke", () => {
  test("renders a HeroUI button without a global provider", () => {
    render(<Button>HeroUI smoke</Button>);

    expect(screen.getByRole("button", { name: "HeroUI smoke" })).toBeInTheDocument();
  });
});
