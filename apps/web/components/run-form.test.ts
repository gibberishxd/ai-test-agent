import { describe, expect, it } from "vitest";
import { initialModel, SERVER_DEFAULT } from "./run-form";

const model = (id: string, fields: { usable?: boolean; isDefault?: boolean } = {}) => ({
  id,
  label: id,
  model: "m",
  usable: true,
  isDefault: false,
  ...fields,
});

describe("model picker", () => {
  it("starts on the workspace default when it passed Test connection", () => {
    expect(initialModel([model("a"), model("b", { isDefault: true })])).toBe("b");
  });

  it("falls back to the server's model when the default isn't usable or there is none", () => {
    expect(initialModel([model("a", { isDefault: true, usable: false })])).toBe(SERVER_DEFAULT);
    expect(initialModel([model("a")])).toBe(SERVER_DEFAULT);
  });
});
