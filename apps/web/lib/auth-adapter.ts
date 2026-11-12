/**
 * A small Auth.js (v4) adapter over our Prisma client.
 *
 * Why not the stock Prisma adapter: in our schema every user belongs to a workspace, so
 * creating a user must also create their workspace, in one transaction. The stock adapter
 * can't do that. Auth.js only needs these methods with JWT sessions.
 */
import type { Adapter, AdapterAccount, AdapterUser, VerificationToken } from "next-auth/adapters";
import type { PrismaClient } from "@/lib/generated/prisma/client";
import { inTenant } from "@/lib/tenant-db";

export type AppUser = AdapterUser & { workspaceId: string };

type DbUser = {
  id: string;
  email: string;
  name: string | null;
  image: string | null;
  emailVerified: Date | null;
  workspaceId: string;
};

const toAdapterUser = (user: DbUser): AppUser => ({
  id: user.id,
  email: user.email,
  name: user.name,
  image: user.image,
  emailVerified: user.emailVerified,
  workspaceId: user.workspaceId,
});

/** "ada@example.com" → "ada-3f9c": readable and unique enough for a workspace slug. */
export function workspaceSlug(email: string, suffix: string): string {
  const base = email.split("@")[0].toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return `${base || "workspace"}-${suffix}`;
}

/**
 * Create a user and their personal workspace together. The new workspace's id is chosen here,
 * so the whole thing runs inside that workspace (row-level security allows exactly this).
 */
export async function createUserWithWorkspace(
  _db: PrismaClient,
  data: { email: string; name?: string | null; image?: string | null; emailVerified?: Date | null },
): Promise<AppUser> {
  const workspaceId = crypto.randomUUID();
  const user = await inTenant(workspaceId, async (tx) => {
    const workspace = await tx.workspace.create({
      data: {
        id: workspaceId,
        name: `${data.name || data.email.split("@")[0]}'s workspace`,
        slug: workspaceSlug(data.email, crypto.randomUUID().slice(0, 4)),
      },
    });
    return tx.user.create({
      data: {
        email: data.email.toLowerCase(),
        name: data.name ?? null,
        image: data.image ?? null,
        emailVerified: data.emailVerified ?? null,
        workspaceId: workspace.id,
        role: "owner", // whoever creates a workspace owns it
      },
    });
  });
  return toAdapterUser(user);
}

export function appAdapter(db: PrismaClient): Adapter {
  return {
    createUser: (user: Omit<AdapterUser, "id">) => createUserWithWorkspace(db, user),

    async getUser(id) {
      const user = await db.user.findUnique({ where: { id } });
      return user ? toAdapterUser(user) : null;
    },

    async getUserByEmail(email) {
      const user = await db.user.findUnique({ where: { email: email.toLowerCase() } });
      return user ? toAdapterUser(user) : null;
    },

    async getUserByAccount({ provider, providerAccountId }) {
      const account = await db.account.findUnique({
        where: { provider_providerAccountId: { provider, providerAccountId } },
        include: { user: true },
      });
      return account ? toAdapterUser(account.user) : null;
    },

    async updateUser({ id, ...data }) {
      // Reading the user is allowed before the workspace is known; the write happens inside it.
      const { workspaceId } = await db.user.findUniqueOrThrow({ where: { id }, select: { workspaceId: true } });
      const user = await inTenant({ workspaceId, userId: id }, (tx) =>
        tx.user.update({ where: { id }, data: { name: data.name, image: data.image, emailVerified: data.emailVerified } }),
      );
      return toAdapterUser(user);
    },

    async linkAccount(account: AdapterAccount) {
      await db.account.create({
        data: {
          userId: account.userId,
          type: account.type,
          provider: account.provider,
          providerAccountId: account.providerAccountId,
          refreshToken: account.refresh_token ?? null,
          accessToken: account.access_token ?? null,
          expiresAt: account.expires_at ?? null,
          tokenType: account.token_type ?? null,
          scope: account.scope ?? null,
          idToken: account.id_token ?? null,
          sessionState: (account.session_state as string | undefined) ?? null,
        },
      });
    },

    async createVerificationToken(token: VerificationToken) {
      return db.verificationToken.create({ data: token });
    },

    async useVerificationToken({ identifier, token }) {
      // Single use: deleting it is what makes a magic link work only once.
      try {
        return await db.verificationToken.delete({ where: { identifier_token: { identifier, token } } });
      } catch {
        return null;
      }
    },
  };
}
