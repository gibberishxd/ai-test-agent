import { describe, expect, it } from "vitest";
import { SOCKET_ADDRESS_HEADER, stampSocketAddress, stampingEmit } from "./socket-address";

function request(remoteAddress: string | undefined, headers: Record<string, string> = {}) {
  return { headers, socket: { remoteAddress } } as never as Parameters<typeof stampSocketAddress>[0];
}

describe("socket address stamp", () => {
  it("overwrites a value the client sent with the real peer address", () => {
    const req = request("203.0.113.7", { [SOCKET_ADDRESS_HEADER]: "6.6.6.6" });
    stampSocketAddress(req);
    expect(req.headers[SOCKET_ADDRESS_HEADER]).toBe("203.0.113.7");
  });

  it("unwraps an IPv4 address written as IPv6", () => {
    const req = request("::ffff:203.0.113.7");
    stampSocketAddress(req);
    expect(req.headers[SOCKET_ADDRESS_HEADER]).toBe("203.0.113.7");
  });

  it("stamps request events and passes every event on unchanged", () => {
    const seen: unknown[][] = [];
    const emit = stampingEmit((...args: unknown[]) => {
      seen.push(args);
      return true;
    });
    const req = request("203.0.113.7");
    expect(emit.call({}, "request", req, "res")).toBe(true);
    emit.call({}, "listening");
    expect(req.headers[SOCKET_ADDRESS_HEADER]).toBe("203.0.113.7");
    expect(seen).toEqual([["request", req, "res"], ["listening"]]);
  });
});
