/** Runs once when the Next.js server starts (Node runtime only). */
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  const { Server } = await import("node:http");
  const { stampingEmit } = await import("./lib/socket-address");
  type Emit = import("./lib/socket-address").Emit;
  const marked = Server.prototype as typeof Server.prototype & { __stamped?: boolean };
  if (marked.__stamped) return; // dev mode can call register() more than once
  marked.__stamped = true;
  Server.prototype.emit = stampingEmit(Server.prototype.emit as Emit) as typeof Server.prototype.emit;
}
