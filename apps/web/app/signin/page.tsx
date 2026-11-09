import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { SignInOptions } from "@/components/auth-buttons";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { currentUser, enabledProviders } from "@/lib/auth";

export const metadata: Metadata = { title: "Sign in" };

export default async function SignInPage(props: PageProps<"/signin">) {
  if (await currentUser()) redirect("/dashboard");
  const params = await props.searchParams;
  const checkEmail = params["check-email"] !== undefined;
  const error = typeof params.error === "string" ? params.error : null;

  return (
    <main className="mx-auto grid max-w-md gap-6 px-4 py-16">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">{checkEmail ? "Check your email" : "Sign in"}</CardTitle>
          <CardDescription>
            {checkEmail
              ? "We sent you a sign-in link. It works once and expires in 24 hours."
              : "Sign in to test your own apps, verify domains for interactive tests and share reports."}
          </CardDescription>
        </CardHeader>
        {!checkEmail && (
          <CardContent className="grid gap-4">
            {error && (
              <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
                Sign-in didn&apos;t work ({error}). Try again or use another method.
              </p>
            )}
            <SignInOptions {...enabledProviders()} />
          </CardContent>
        )}
      </Card>
    </main>
  );
}
