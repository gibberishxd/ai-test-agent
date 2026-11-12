import { describe, expect, it } from "vitest";
import { presignedUrl, storageConfig } from "./storage";

const env = {
  STORAGE: "s3",
  S3_BUCKET: "screenshots",
  S3_REGION: "us-east-1",
  S3_ENDPOINT: "http://minio:9000",
  S3_PUBLIC_ENDPOINT: "http://localhost:9000",
  S3_ACCESS_KEY: "minio",
  S3_SECRET_KEY: "minio-secret",
};

describe("storage", () => {
  it("is local disk unless STORAGE=s3", () => {
    expect(storageConfig({})).toEqual({ mode: "local" });
    expect(storageConfig(env)).toMatchObject({ mode: "s3", bucket: "screenshots", publicEndpoint: "http://localhost:9000" });
  });

  it("gives a signed link that expires, for the browser's address of the store", async () => {
    const config = storageConfig(env);
    if (config.mode !== "s3") throw new Error("expected s3");
    const url = new URL(await presignedUrl(config, "run-1/page-001.png", 300));
    expect(url.origin).toBe("http://localhost:9000");
    expect(url.pathname).toBe("/screenshots/run-1/page-001.png");
    expect(url.searchParams.get("X-Amz-Expires")).toBe("300");
    expect(url.searchParams.get("X-Amz-Signature")).toMatch(/^[0-9a-f]{64}$/);
    expect(url.toString()).not.toContain("minio-secret");
  });
});
