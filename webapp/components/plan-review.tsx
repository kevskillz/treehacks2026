'use client';

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { approvePlan } from "@/app/actions";

type PlanReviewProps = {
  planId: string;
  initialContent?: string;
  projectStatus?: string;
};

export function PlanReview({ planId, initialContent, projectStatus }: PlanReviewProps) {
  const isAlreadyApproved = projectStatus === "completed" || projectStatus === "executing";
  const [content, setContent] = useState(initialContent || "");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [approved, setApproved] = useState(isAlreadyApproved);
  const [activeTab, setActiveTab] = useState<"edit" | "preview">("edit");

  const onApprove = async () => {
    setIsSubmitting(true);
    setMessage(null);
    try {
      const result = await approvePlan(planId, content);
      if (result?.error) {
        setMessage(`Error: ${result.error}`);
        return;
      }
      setApproved(true);
      setMessage("Plan approved. Moving to code execution.");
    } catch (err) {
      setMessage(`Error: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-4 rounded-2xl border border-border/70 bg-card p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Plan Review</p>
          <p className="text-sm text-muted-foreground/80">Edit the plan and approve to proceed.</p>
        </div>
        <Button
          variant="xai"
          size="sm"
          onClick={onApprove}
          disabled={isSubmitting || approved}
          className="min-w-[140px]"
        >
          {isSubmitting ? "Approving..." : approved ? "Approved" : "Approve plan"}
        </Button>
      </div>

      <div className="space-y-3">
        <div className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/30 p-1 text-xs text-muted-foreground">
          <button
            className={`rounded-full px-3 py-1 transition ${
              activeTab === "edit" ? "bg-foreground text-background" : "hover:text-foreground"
            }`}
            onClick={() => setActiveTab("edit")}
            disabled={approved}
          >
            Edit
          </button>
          <button
            className={`rounded-full px-3 py-1 transition ${
              activeTab === "preview" ? "bg-foreground text-background" : "hover:text-foreground"
            }`}
            onClick={() => setActiveTab("preview")}
          >
            Preview
          </button>
        </div>

        {activeTab === "edit" ? (
          <textarea
            className="min-h-[320px] w-full rounded-lg border border-border/60 bg-background p-3 text-sm text-foreground focus:border-foreground/60 focus:outline-none"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            disabled={approved}
          />
        ) : (
          <div className="prose prose-neutral dark:prose-invert max-w-none rounded-lg border border-border/60 bg-background p-4 text-foreground">
            <ReactMarkdown>
              {content || "*No content provided.*"}
            </ReactMarkdown>
          </div>
        )}
      </div>

      {message && (
        <div
          className={`rounded-lg border px-3 py-2 text-sm ${
            message.startsWith("Error")
              ? "border-red-300 bg-red-50 text-red-700 dark:border-red-500/40 dark:bg-red-500/5 dark:text-red-300"
              : "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-500/5 dark:text-emerald-300"
          }`}
        >
          {message}
        </div>
      )}
    </div>
  );
}
