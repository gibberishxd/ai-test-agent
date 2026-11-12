import { describe, expect, it } from "vitest";
import { fileUrl } from "./file-url";

describe("fileUrl", () => {
  it("is the plain files route for the owner", () => {
    expect(fileUrl("run-1/page-001.png")).toBe("/api/files/run-1/page-001.png");
  });

  it("carries the share token on a shared report", () => {
    expect(fileUrl("run-1/page-001.png", "tok_en-1")).toBe("/api/files/run-1/page-001.png?share=tok_en-1");
  });
});
