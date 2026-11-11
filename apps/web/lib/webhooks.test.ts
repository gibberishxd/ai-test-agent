import { describe, expect, it } from "vitest";
import { generateWebhookSecret, webhookUrlError } from "./webhooks";

describe("webhookUrlError", () => {
  it("accepts public http(s) URLs", () => {
    expect(webhookUrlError("https://hooks.example.com/ata")).toBeNull();
    expect(webhookUrlError("http://ci.example.org:8080/hook")).toBeNull();
  });

  it("refuses other schemes, credentials in the URL, and obvious internal addresses", () => {
    for (const url of [
      "ftp://example.com/",
      "https://user:pass@example.com/",
      "http://localhost:4000/",
      "http://127.0.0.1/",
      "http://10.1.2.3/",
      "http://192.168.0.10/",
      "http://169.254.169.254/latest/meta-data",
      "http://[::1]/",
      "not a url",
    ]) {
      expect(webhookUrlError(url), url).not.toBeNull();
    }
  });
});

describe("generateWebhookSecret", () => {
  it("is a long random secret with a recognisable prefix", () => {
    const a = generateWebhookSecret();
    expect(a.startsWith("whsec_")).toBe(true);
    expect(a.length).toBeGreaterThanOrEqual(40);
    expect(a).not.toBe(generateWebhookSecret());
  });
});
