'use client'

import { Button } from "@/components/ui/button";
import { useMemo, useState } from "react";
import { startBuild } from "@/app/actions";
import { Check, FilePlus2, GitPullRequest, Sparkles } from "lucide-react";

interface CreateButtonProps {
  automationId: string;
  hasIssue?: boolean;
  planId?: string;
  issueUrl?: string;
  issueNumber?: number;
  projectStatus?: string;
  prUrl?: string;
  prNumber?: number;
}

export function CreateButton({ automationId, hasIssue, planId, issueUrl, issueNumber, projectStatus, prUrl, prNumber }: CreateButtonProps) {
  const initialStage = (() => {
    // Derive stage from database project status first
    if (projectStatus === "completed" || projectStatus === "executing") return "pr" as const;
    if (projectStatus === "provisioning" || projectStatus === "planning") return "plan" as const;
    if (planId) return "plan" as const;
    if (hasIssue) return "issue" as const;
    return "idle" as const;
  })();

  const [stage, setStage] = useState<"idle" | "issue" | "plan" | "pr">(initialStage);
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [issueLink, setIssueLink] = useState<string | undefined>(issueUrl);
  const [issueNum, setIssueNum] = useState<number | undefined>(issueNumber);

  const steps = useMemo(
    () => [
      {
        key: "issue" as const,
        title: "Issue created",
        description: "Track the request",
        icon: <FilePlus2 className="h-4 w-4" />,
      },
      {
        key: "plan" as const,
        title: "Plan ready",
        description: "Implementation outline",
        icon: <Sparkles className="h-4 w-4" />,
      },
      {
        key: "pr" as const,
        title: "PR opened",
        description: "Review & merge",
        icon: <GitPullRequest className="h-4 w-4" />,
      },
    ],
    []
  );

  const handleCreate = async () => {
    setIsLoading(true);
    setMessage(null);

    try {
      const result = await startBuild(automationId);
      if (result?.error) {
        setMessage(`Error: ${result.error}`);
      } else {
        setStage("issue");
        setMessage("GitHub issue created");
        setIssueLink(result.issueUrl);
        setIssueNum(result.issueNumber);
      }
    } catch (error) {
      setMessage(`Error: ${error instanceof Error ? error.message : "An error occurred"}`);
    } finally {
      setIsLoading(false);
    }
  };

  const renderPipeline = () => {
    const currentIndex = Math.max(
      steps.findIndex((step) => step.key === stage),
      0
    );

    return (
      <div className="relative overflow-hidden rounded-xl border border-border/60 bg-muted/20 p-4">
        <div className="relative flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Build pipeline</p>
              <p className="text-sm text-muted-foreground/90">We keep going until the PR is ready.</p>
            </div>
            <div className="flex items-center gap-3">
              {issueLink && (
                <a
                  href={issueLink}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs font-medium text-foreground underline underline-offset-4 hover:text-foreground/70"
                >
                  {issueNum ? `Issue #${issueNum}` : "View issue"}
                </a>
              )}
              {prUrl && (
                <a
                  href={prUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs font-medium text-foreground underline underline-offset-4 hover:text-foreground/70"
                >
                  {prNumber ? `PR #${prNumber}` : "View PR"}
                </a>
              )}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            {steps.map((step, index) => {
              const isDone = index < currentIndex;
              const isActive = index === currentIndex;

              const stateClasses = isDone
                ? "border-emerald-500/30 bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
                : isActive
                ? "border-foreground/20 bg-foreground/5 text-foreground"
                : "border-border bg-card text-muted-foreground";

              return (
                <div
                  key={step.key}
                  className="group relative rounded-lg border p-3 transition duration-200 hover:-translate-y-[2px] hover:border-foreground/30 hover:shadow-md"
                >
                  {index < steps.length - 1 && (
                    <div className="absolute right-[-10%] top-1/2 hidden h-px w-[20%] -translate-y-1/2 bg-border sm:block" />
                  )}
                  <div className="flex items-center gap-3">
                    <div className={`flex h-10 w-10 items-center justify-center rounded-full border ${stateClasses}`}>
                      {isDone ? <Check className="h-4 w-4" /> : step.icon}
                    </div>
                    <div className="space-y-0.5">
                      <p className={`text-sm font-semibold ${isActive ? "text-foreground" : ""}`}>
                        {step.title}
                      </p>
                      <p className="text-xs text-muted-foreground">{step.description}</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-3">
      {stage === "idle" ? (
        <Button
          variant="xai"
          size="default"
          className="gap-2"
          onClick={handleCreate}
          disabled={isLoading}
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          {isLoading ? "Building..." : "Build"}
        </Button>
      ) : (
        renderPipeline()
      )}
      {message && (
        <div
          className={`rounded-lg border px-3 py-2 text-sm ${
            message.startsWith("Error")
              ? "border-red-300 bg-red-50 text-red-700 dark:border-red-500/40 dark:bg-red-500/5 dark:text-red-300"
              : "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-500/5 dark:text-emerald-300"
          }`}
        >
          {message}
          {message.toLowerCase().includes("error")
            ? null
            : issueLink && (
                <span className="ml-2">
                  {issueNum ? `#${issueNum} · ` : ""}
                  <a
                    href={issueLink}
                    className="underline underline-offset-4 hover:text-foreground"
                    target="_blank"
                    rel="noreferrer"
                  >
                    View
                  </a>
                </span>
              )}
        </div>
      )}
    </div>
  );
}
