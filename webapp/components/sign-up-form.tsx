"use client";

import { cn } from "@/lib/utils";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

const requirePositiveString = (value?: string): value is string => {
  return typeof value === "string" && value.trim().length > 0;
};

const normalizeHandle = (value: string) => {
  const trimmed = value.trim();
  if (!trimmed) return "";
  return trimmed.startsWith("@") ? trimmed : `@${trimmed}`;
};

const parseGithubRepo = (input: string) => {
  const cleaned = input.trim().replace(/^https?:\/\/github\.com\//i, "");
  const parts = cleaned.split("/").filter(Boolean);
  if (parts.length >= 2) {
    return { owner: parts[0], repo: parts[1] };
  }
  // Minimal parsing fallback: treat the whole input as both owner and repo to avoid blocking signup
  return { owner: cleaned || "default-owner", repo: cleaned || "default-repo" };
};

export function SignUpForm({
  className,
  ...props
}: React.ComponentPropsWithoutRef<"div">) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [repeatPassword, setRepeatPassword] = useState("");
  const [xHandle, setXHandle] = useState("");
  const [githubRepo, setGithubRepo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const router = useRouter();

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    const supabase = createClient();
    setIsLoading(true);
    setError(null);

    if (!requirePositiveString(xHandle)) {
      setError("App X handle is required");
      setIsLoading(false);
      return;
    }

    if (!requirePositiveString(githubRepo)) {
      setError("Project GitHub repository is required");
      setIsLoading(false);
      return;
    }

    if (password !== repeatPassword) {
      setError("Passwords do not match");
      setIsLoading(false);
      return;
    }

    try {
      const normalizedHandle = normalizeHandle(xHandle);
      const { owner: parsedOwner, repo: parsedRepo } = parseGithubRepo(githubRepo);

      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: `${window.location.origin}/features`,
        },
      });
      if (error) throw error;

      const userId = data?.user?.id;
      if (!userId) {
        throw new Error("User ID missing after sign up");
      }

      // Create default repo config for the account
      const { data: repoConfig, error: repoError } = await supabase
        .from("repo_configs")
        .insert({
          github_owner: parsedOwner,
          github_repo: parsedRepo,
          github_branch: "main",
          x_account_handle: normalizedHandle,
          x_keywords: [],
          local_agent_enabled: false,
          auto_create_issues: false,
          auto_create_prs: false,
          user_id: userId,
        })
        .select()
        .single();

      if (repoError) throw repoError;

      // Store account profile with default repo config
      const { error: accountError } = await supabase.from("accounts").insert({
        id: userId,
        x_account_handle: normalizedHandle,
        github_owner: parsedOwner,
        github_repo: parsedRepo,
        github_branch: "main",
        default_repo_config_id: repoConfig?.id ?? null,
      });

      if (accountError) throw accountError;
      router.push("/auth/sign-up-success");
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className={cn("flex flex-col gap-6", className)} {...props}>
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Sign up</CardTitle>
          <CardDescription>Create a new account</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSignUp}>
            <div className="flex flex-col gap-6">
              <div className="grid gap-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="m@example.com"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <div className="flex items-center">
                  <Label htmlFor="password">Password</Label>
                </div>
                <Input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <div className="flex items-center">
                  <Label htmlFor="repeat-password">Repeat Password</Label>
                </div>
                <Input
                  id="repeat-password"
                  type="password"
                  required
                  value={repeatPassword}
                  onChange={(e) => setRepeatPassword(e.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="x-handle">App X handle</Label>
                <Input
                  id="x-handle"
                  type="text"
                  placeholder="@yourapp"
                  required
                  value={xHandle}
                  onChange={(e) => setXHandle(e.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="github-repo">Project GitHub repository</Label>
                <Input
                  id="github-repo"
                  type="text"
                  placeholder="owner/repo or https://github.com/owner/repo"
                  required
                  value={githubRepo}
                  onChange={(e) => setGithubRepo(e.target.value)}
                />
              </div>
              {error && <p className="text-sm text-red-500">{error}</p>}
              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? "Creating an account..." : "Sign up"}
              </Button>
            </div>
            <div className="mt-4 text-center text-sm">
              Already have an account?{" "}
              <Link href="/auth/login" className="underline underline-offset-4">
                Login
              </Link>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
