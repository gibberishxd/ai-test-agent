import NextAuth from "next-auth";
import { authOptions } from "@/lib/auth";

// Auth.js handles sign-in, callbacks and sign-out under /api/auth/*.
const handler = NextAuth(authOptions);

export { handler as GET, handler as POST };
