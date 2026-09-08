import { describe, expect, it } from "vitest";
import { isApiKeyDeleteCommand } from "@lib/settings-input";

describe("isApiKeyDeleteCommand", () => {
  it("accepts only the explicit normalized delete command", () => {
    expect(isApiKeyDeleteCommand(" delete ")).toBe(true);
    expect(isApiKeyDeleteCommand("DELETE")).toBe(true);
    expect(isApiKeyDeleteCommand("delete-my-key")).toBe(false);
  });
});
