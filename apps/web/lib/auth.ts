/**
 * Sign-in (Auth.js v4). Providers switch on only when configured in .env:
 * - GitHub OAuth: AUTH_GITHUB_ID + AUTH_GITHUB_SECRET
 * - Email magic link: EMAIL_SERVER (an SMTP URL) + EMAIL_FROM
 * - "Sign in as demo user": development only, never in production
 * Sessions are JWTs (signed with NEXTAUTH_SECRET) carrying the user id and workspace id.
 */
import { getServerSession, type NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import EmailProvider from "next-auth/providers/email";
import GitHubProvider from "next-auth/providers/github";
import { appAdapter, createUserWithWorkspace, type AppUser } from "@/lib/auth-adapter";
import { db } from "@/lib/db";

export const DEMO_USER_EMAIL = "demo-user@example.com";

export function demoLoginEnabled(): boolean {
  return process.env.NODE_ENV !== "production";
}

export function enabledProviders() {
  return {
    github: Boolean(process.env.AUTH_GITHUB_ID && process.env.AUTH_GITHUB_SECRET),
    email: Boolean(process.env.EMAIL_SERVER && process.env.EMAIL_FROM),
    demo: demoLoginEnabled(),
  };
}

function providers(): NextAuthOptions["providers"] {
  const enabled = enabledProviders();
  const list: NextAuthOptions["providers"] = [];
  if (enabled.github) {
    list.push(
      GitHubProvider({
        clientId: process.env.AUTH_GITHUB_ID!,
        clientSecret: process.env.AUTH_GITHUB_SECRET!,
      }),
    );
  }
  if (enabled.email) {
    list.push(EmailProvider({ server: process.env.EMAIL_SERVER, from: process.env.EMAIL_FROM }));
  }
  if (enabled.demo) {
    list.push(
      CredentialsProvider({
        id: "demo",
        name: "Demo user",
        credentials: {},
        async authorize() {
          const existing = await db.user.findUnique({ where: { email: DEMO_USER_EMAIL } });
          if (existing) return { ...existing, image: existing.image ?? undefined };
          return createUserWithWorkspace(db, { email: DEMO_USER_EMAIL, name: "Demo User" });
        },
      }),
    );
  }
  return list;
}

export const authOptions: NextAuthOptions = {
  adapter: appAdapter(db),
  providers: providers(),
  session: { strategy: "jwt" },
  // Only for local development; production must set NEXTAUTH_SECRET. `||`, not `??`: an empty
  // NEXTAUTH_SECRET= line in .env must fall back too (an empty key can't encrypt the JWT).
  secret:
    process.env.NEXTAUTH_SECRET ||
    (process.env.NODE_ENV === "production" ? undefined : "dev-only-secret-not-for-production"),
  pages: { signIn: "/signin", verifyRequest: "/signin?check-email=1" },
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.uid = user.id;
        token.workspaceId = (user as AppUser).workspaceId;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.id = token.uid as string;
        session.user.workspaceId = token.workspaceId as string;
      }
      return session;
    },
  },
};

export type SessionUser = { id: string; workspaceId: string; email: string; name: string | null };

/** The signed-in user, or null for a visitor. */
export async function currentUser(): Promise<SessionUser | null> {
  const session = await getServerSession(authOptions);
  const user = session?.user;
  if (!user?.id || !user.workspaceId || !user.email) return null;
  return { id: user.id, workspaceId: user.workspaceId, email: user.email, name: user.name ?? null };
}
