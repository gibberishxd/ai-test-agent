import "next-auth";

// Our sessions also carry the user's id and workspace id (set in the jwt/session callbacks).
declare module "next-auth" {
  interface Session {
    user?: {
      id: string;
      workspaceId: string;
      name?: string | null;
      email?: string | null;
      image?: string | null;
    };
  }
}
