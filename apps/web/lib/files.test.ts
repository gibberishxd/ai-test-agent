import { describe, expect, it } from "vitest";
import { resolveKey, runIdOfKey } from "./files";

describe("resolveKey", () => {
  it("maps a key inside the data folder", () => {
    expect(resolveKey("/data", "abc/page-001.png")).toBe("/data/abc/page-001.png");
  });

  it("refuses keys that escape the folder", () => {
    expect(resolveKey("/data", "../etc/passwd.png")).toBeNull();
    expect(resolveKey("/data", "abc/../../secret.png")).toBeNull();
  });

  it("serves images only", () => {
    expect(resolveKey("/data", "abc/notes.txt")).toBeNull();
  });
});

describe("runIdOfKey", () => {
  it("takes the first path segment", () => {
    expect(runIdOfKey("7816e5b6-9d40-4160-8fd3-2bb85b10f0cb/page-001.png")).toBe(
      "7816e5b6-9d40-4160-8fd3-2bb85b10f0cb",
    );
  });
});
