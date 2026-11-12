/**
 * The address a request really came from: the TCP socket's peer, which a client can't fake
 * (unlike the X-Forwarded-For header, which is just text the client may send).
 *
 * Next.js route handlers only get headers, not the socket. So when the server starts
 * (instrumentation.ts) every incoming request is stamped with its socket address in a header
 * of our own, overwriting anything the client sent under that name.
 */
import type { IncomingMessage } from "node:http";

export const SOCKET_ADDRESS_HEADER = "x-socket-address";

/** Overwrite our header with the socket's peer address ("::ffff:1.2.3.4" → "1.2.3.4"). */
export function stampSocketAddress(request: Pick<IncomingMessage, "headers" | "socket">): void {
  const address = request.socket?.remoteAddress ?? "";
  request.headers[SOCKET_ADDRESS_HEADER] = address.replace(/^::ffff:/, "");
}

/** The shape of EventEmitter's `emit`, loosely typed: we pass every event through untouched. */
export type Emit = (this: unknown, event: string | symbol, ...args: unknown[]) => boolean;

/** Wrap `emit` so every "request" event is stamped before any handler sees it. */
export function stampingEmit(emit: Emit): Emit {
  return function (this: unknown, event, ...args) {
    if (event === "request" && args[0]) stampSocketAddress(args[0] as IncomingMessage);
    return emit.call(this, event, ...args);
  };
}
