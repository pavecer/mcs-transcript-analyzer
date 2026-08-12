import { describe, expect, it } from "vitest";
import { parseWholeNumberInput } from "./wholeNumberInput";

describe("parseWholeNumberInput", () => {
  it("keeps a cleared field invalid instead of coercing it to zero", () => {
    expect(parseWholeNumberInput("")).toBeNull();
    expect(parseWholeNumberInput("   ")).toBeNull();
  });

  it("accepts non-negative whole numbers", () => {
    expect(parseWholeNumberInput("0")).toBe(0);
    expect(parseWholeNumberInput("125")).toBe(125);
  });

  it("rejects fractional, negative, and non-numeric values", () => {
    expect(parseWholeNumberInput("0.5")).toBeNull();
    expect(parseWholeNumberInput("-1")).toBeNull();
    expect(parseWholeNumberInput("nope")).toBeNull();
  });
});