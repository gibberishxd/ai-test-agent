import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { AcceptInvitation } from "@/components/accept-invitation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { invitationPreview } from "@/lib/members";
import { currentContext } from "@/lib/workspace";

export const metadata: Metadata = { title: "Invitation" };

export default async function InvitePage(props: { params: Promise<{ token: string }> }) {
  await connection();
  const { token } = await props.params;
  const [invite, context] = await Promise.all([invitationPreview(token), currentContext()]);
  return (
    <main className="mx-auto grid max-w-md px-4 py-16">
      <Card>
        {invite ? (
          <>
            <CardHeader>
              <CardTitle>Join {invite.workspaceName}</CardTitle>
              <CardDescription>
                You&apos;re invited as <strong>{invite.role}</strong>. The link expires on {new Date(invite.expiresAt).toLocaleDateString()}.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {context.signedIn ? (
                <AcceptInvitation token={token} />
              ) : (
                <Button asChild>
                  <Link href={`/signin?callbackUrl=${encodeURIComponent(`/invite/${token}`)}`}>Sign in to join</Link>
                </Button>
              )}
            </CardContent>
          </>
        ) : (
          <CardHeader>
            <CardTitle>This invitation isn&apos;t valid</CardTitle>
            <CardDescription>It may have expired, been used or been revoked. Ask whoever invited you for a new link.</CardDescription>
          </CardHeader>
        )}
      </Card>
    </main>
  );
}
