"use client";

import { type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { CreateButton } from "@/components/create-button";
import { Heart, MessageCircle, Repeat2, BarChart3, Share, MoreHorizontal, Verified } from "lucide-react";
import { PlanReview } from "@/components/plan-review";

interface Tweet {
  id: string;
  tweet_id: string;
  tweet_text: string;
  tweet_author_username: string;
  tweet_created_at: string;
  likes_count: number;
  retweets_count: number;
  replies_count: number;
  views_count?: number;
}

interface ProjectDetailProps {
  id: string;
  displayName: string;
  displayDescription: string;
  displayStatus: string;
  displayTrigger: string;
  displayAction: string;
  displayRepo?: string;
  displayHandle?: string;
  relatedTweets: Tweet[];
  planId?: string;
  planContent?: string;
  projectStatus: string;
  backendUrl: string;
  hasIssue?: boolean;
  issueUrl?: string;
  issueNumber?: number;
}

const STATUS_OPTIONS = [
  { value: "pending", label: "Pending" },
  { value: "planning", label: "Planning" },
  { value: "provisioning", label: "Provisioning" },
  { value: "executing", label: "Executing" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "closed", label: "Closed" },
];

function getStatusLabel(status: string): string {
  return STATUS_OPTIONS.find((s) => s.value === status)?.label || status;
}

function formatCount(count: number): string {
  if (count >= 1000000) {
    return (count / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
  }
  if (count >= 1000) {
    return (count / 1000).toFixed(1).replace(/\.0$/, "") + "K";
  }
  return count.toString();
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffHours = diffMs / (1000 * 60 * 60);

  if (diffHours < 24) {
    return `${Math.floor(diffHours)}h`;
  }

  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function MetricPill({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-1 rounded-full border border-border/50 bg-muted/30 px-2.5 py-1 text-xs text-muted-foreground">
      <span className="text-muted-foreground">{icon}</span>
      <span className="font-medium text-foreground">{value}</span>
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground/80">{label}</span>
    </div>
  );
}

function TweetCard({ tweet }: { tweet: Tweet }) {
  return (
    <div
      className="group relative cursor-pointer overflow-hidden px-5 py-4 transition duration-200 hover:bg-accent/50"
    >
      <div className="relative flex gap-3">
        <div className="flex-shrink-0">
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-muted border border-border/60 text-foreground/90">
            <span className="text-sm font-bold">
              {tweet.tweet_author_username.charAt(0).toUpperCase()}
            </span>
          </div>
        </div>

        <div className="min-w-0 flex-1 space-y-2.5">
          <div className="flex items-center gap-1 text-sm text-muted-foreground">
            <span className="truncate font-semibold text-foreground">{tweet.tweet_author_username}</span>
            <Verified className="h-4 w-4 text-blue-400 flex-shrink-0" />
            <span className="text-muted-foreground text-sm">@{tweet.tweet_author_username}</span>
            <span className="text-muted-foreground text-sm">&middot;</span>
            <span className="text-muted-foreground text-sm hover:text-foreground/80">
              {formatDate(tweet.tweet_created_at)}
            </span>
            <div className="ml-auto">
              <Button
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0 rounded-full hover:bg-accent"
              >
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <p className="text-[15px] leading-6 text-foreground/90 whitespace-pre-wrap">
            {tweet.tweet_text}
          </p>

          <div className="flex flex-wrap items-center gap-2">
            <MetricPill icon={<MessageCircle className="h-3.5 w-3.5" />} label="replies" value={formatCount(tweet.replies_count)} />
            <MetricPill icon={<Repeat2 className="h-3.5 w-3.5" />} label="retweets" value={formatCount(tweet.retweets_count)} />
            <MetricPill icon={<Heart className="h-3.5 w-3.5" />} label="likes" value={formatCount(tweet.likes_count)} />
            <MetricPill
              icon={<BarChart3 className="h-3.5 w-3.5" />}
              label="views"
              value={formatCount(tweet.views_count || (tweet.likes_count + tweet.retweets_count) * 50)}
            />
            <button className="ml-auto flex items-center gap-2 rounded-full border border-border/60 px-3 py-1.5 text-xs text-muted-foreground transition hover:border-foreground/40 hover:text-foreground">
              <Share className="h-3.5 w-3.5" />
              Share
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ProjectDetail({
  id,
  displayName,
  displayDescription,
  displayStatus,
  displayRepo,
  displayHandle,
  relatedTweets,
  planId,
  planContent,
  projectStatus,
  backendUrl,
  hasIssue,
  issueUrl,
  issueNumber,
}: ProjectDetailProps) {
  return (
    <div className="min-h-screen p-8 lg:p-16">
      <div className="mx-auto max-w-4xl space-y-8">
        {/* Header */}
        <div className="space-y-2 px-1">
          <div className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/30 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            Project
            {displayRepo && (
              <span className="rounded-full bg-foreground/5 px-2 py-0.5 text-[11px] font-medium text-foreground/70">
                {displayRepo}
              </span>
            )}
          </div>
          <div className="space-y-1">
            <h1 className="text-3xl font-semibold text-foreground leading-tight">{displayName}</h1>
            <p className="text-sm text-muted-foreground max-w-2xl">{displayDescription || "No description provided."}</p>
          </div>
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            {displayHandle && <span className="rounded-full border border-border/60 px-3 py-1">Monitoring @{displayHandle}</span>}
          </div>
        </div>

        {/* Build / Pipeline only */}
        <div className="space-y-3 rounded-2xl border border-border/50 bg-card p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="flex flex-col gap-1">
              <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Build pipeline</p>
              <p className="text-xs text-muted-foreground/80">Shipping until the PR is ready.</p>
            </div>
            <span className="rounded-full border border-border/70 bg-muted/30 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              {getStatusLabel(displayStatus)}
            </span>
          </div>
          <div className="h-px w-full bg-border/70" />
          <CreateButton
            automationId={id}
            hasIssue={hasIssue}
            planId={planId}
            issueUrl={issueUrl}
            issueNumber={issueNumber}
          />
        </div>

        {projectStatus === "provisioning" && planId && (
          <PlanReview planId={planId} initialContent={planContent} />
        )}

        {relatedTweets && relatedTweets.length > 0 && (
          <div className="space-y-2 rounded-2xl border border-border/50 bg-card p-5">
            <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground/80">Related mentions</p>
            <div className="rounded-xl border border-border/60 overflow-hidden divide-y divide-border/60">
              {relatedTweets.map((tweet) => (
                <TweetCard key={tweet.id} tweet={tweet} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
