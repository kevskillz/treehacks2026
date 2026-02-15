'use client'

import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Heart, MessageCircle, Repeat2, FileText, ArrowUpRight, Github, AtSign } from "lucide-react";

export interface Automation {
  id: string;
  name: string;
  description: string;
  trigger: string;
  action: string;
  status: 'active' | 'paused' | 'draft' | 'pending' | 'failed' | 'completed';
  runsToday: number;
  lastRun?: string;
  engagement?: { likes: number; retweets: number; replies: number; total: number };
  tweetCount?: number;
}

const defaultAutomations: Automation[] = [];

function StatusDot({ status }: { status: Automation['status'] }) {
  const colors = {
    active: 'bg-emerald-500',
    paused: 'bg-amber-400',
    draft: 'bg-slate-300',
    pending: 'bg-blue-400',
    failed: 'bg-red-400',
    completed: 'bg-slate-400',
  };
  return <span className={`h-2 w-2 rounded-full ${colors[status]}`} />;
}

function formatCount(count: number): string {
  if (count >= 1000000) return (count / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
  if (count >= 1000) return (count / 1000).toFixed(1).replace(/\.0$/, "") + "K";
  return count.toString();
}

function ProjectRow({ automation }: { automation: Automation }) {
  return (
    <Link href={`/features/${automation.id}`}>
      <div className="group flex items-center gap-4 rounded-xl border border-transparent bg-white/60 px-5 py-4 transition-all duration-150 hover:border-border hover:bg-white hover:shadow-sm cursor-pointer">
        {/* Status + Name */}
        <StatusDot status={automation.status} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-medium text-foreground truncate">
              {automation.name}
            </h3>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground/60 font-medium">
              {automation.status}
            </span>
          </div>
          <p className="text-xs text-muted-foreground truncate mt-0.5">{automation.description}</p>
        </div>

        {/* Stats */}
        <div className="hidden sm:flex items-center gap-4 text-xs text-muted-foreground">
          {automation.tweetCount !== undefined && automation.tweetCount > 0 && (
            <span className="flex items-center gap-1"><FileText className="h-3 w-3" />{formatCount(automation.tweetCount)}</span>
          )}
          {automation.engagement && (
            <>
              <span className="flex items-center gap-1"><Heart className="h-3 w-3" />{formatCount(automation.engagement.likes)}</span>
              <span className="flex items-center gap-1"><Repeat2 className="h-3 w-3" />{formatCount(automation.engagement.retweets)}</span>
              <span className="flex items-center gap-1"><MessageCircle className="h-3 w-3" />{formatCount(automation.engagement.replies)}</span>
            </>
          )}
        </div>

        {/* Arrow */}
        <ArrowUpRight className="h-4 w-4 text-muted-foreground/40 group-hover:text-foreground transition-colors" />
      </div>
    </Link>
  );
}

interface TickerTweet {
  id: string; tweet_text: string; tweet_author_username: string;
  likes_count: number; retweets_count: number; replies_count: number; tweet_created_at: string;
}

type DashboardContentProps = {
  initialDialogOpen?: boolean;
  automations?: Automation[];
  recentTweets?: TickerTweet[];
};

export function DashboardContent({ initialDialogOpen, automations = defaultAutomations, recentTweets = [] }: DashboardContentProps) {
  const [isDialogOpen, setIsDialogOpen] = useState(initialDialogOpen ?? false);
  const [newProjectName, setNewProjectName] = useState("");
  const [githubRepoUrl, setGithubRepoUrl] = useState("");
  const [xAccountHandle, setXAccountHandle] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [statusFilter, setStatusFilter] = useState<"all" | Automation["status"]>("all");

  useEffect(() => { setIsDialogOpen(initialDialogOpen ?? false); }, [initialDialogOpen]);

  const totalProjects = automations.length;

  const filteredAutomations = useMemo(() => {
    if (statusFilter === "all") return automations;
    return automations.filter((a) => a.status === statusFilter);
  }, [automations, statusFilter]);

  const handleCloseDialog = () => { setIsDialogOpen(false); setNewProjectName(""); setGithubRepoUrl(""); setXAccountHandle(""); };

  const parseGitHubUrl = (url: string): { owner: string; repo: string; branch: string } | null => {
    if (!url.trim()) return null;
    url = url.trim().replace(/\.git$/, '');
    if (/^[^\/]+\/[^\/]+$/.test(url)) { const [owner, repo] = url.split('/'); return { owner, repo, branch: 'main' }; }
    const githubMatch = url.match(/github\.com\/([^\/]+)\/([^\/]+)(?:\/tree\/([^\/]+))?/);
    if (githubMatch) return { owner: githubMatch[1], repo: githubMatch[2], branch: githubMatch[3] || 'main' };
    return null;
  };

  const handleCreateProject = async () => {
    if (!newProjectName.trim() || !githubRepoUrl.trim() || !xAccountHandle.trim()) return;
    const parsed = parseGitHubUrl(githubRepoUrl);
    if (!parsed) { alert('Invalid GitHub repository URL.'); return; }
    setIsCreating(true);
    try {
      const response = await fetch("/api/repos", {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_title: newProjectName.trim(), project_description: newProjectName.trim() || undefined,
          github_owner: parsed.owner, github_repo: parsed.repo, github_branch: parsed.branch,
          x_account_handle: xAccountHandle.trim(), x_keywords: [],
          local_agent_enabled: false, auto_create_issues: false, auto_create_prs: false,
        }),
      });
      if (!response.ok) { const errorData = await response.json(); throw new Error(errorData.error || 'Failed to create project'); }
      handleCloseDialog();
      window.location.reload();
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Failed to create project');
    } finally { setIsCreating(false); }
  };

  // Count active statuses for filter badges
  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = { all: automations.length };
    automations.forEach((a) => { counts[a.status] = (counts[a.status] || 0) + 1; });
    return counts;
  }, [automations]);

  return (
    <div className="min-h-screen overflow-x-hidden">
      {/* Hero header with gradient */}
      <div className="relative overflow-hidden">
        <div
          className="absolute inset-0 opacity-40"
          style={{
            background:
              "linear-gradient(135deg, #a5d8d0 0%, #e8d5e8 40%, #f2b0b0 70%, #dcc4e8 100%)",
          }}
        />
        <div
          className="absolute inset-0 opacity-30"
          style={{
            backgroundSize: "40px 40px",
            backgroundImage:
              "linear-gradient(to right, rgba(255,255,255,0.5) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.5) 1px, transparent 1px)",
          }}
        />
        <div className="relative px-8 pt-12 pb-10 lg:px-14">
          <div className="mx-auto max-w-4xl">
            <div className="flex flex-col gap-1">
              <h1 className="text-3xl font-semibold text-foreground tracking-tight">Projects</h1>
              <p className="text-sm text-muted-foreground">Monitor conversations and ship what your users want.</p>
            </div>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="px-8 py-8 lg:px-14">
        <div className="mx-auto max-w-4xl space-y-6">
          {/* Toolbar */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div className="flex flex-wrap items-center gap-1.5">
              {[
                { key: "all", label: "All" }, { key: "active", label: "Active" },
                { key: "pending", label: "Pending" }, { key: "paused", label: "Paused" },
                { key: "completed", label: "Done" }, { key: "failed", label: "Failed" },
              ].filter((f) => f.key === "all" || (statusCounts[f.key] || 0) > 0).map((f) => (
                <button
                  key={f.key}
                  onClick={() => setStatusFilter(f.key as typeof statusFilter)}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                    statusFilter === f.key
                      ? "bg-foreground text-background"
                      : "text-muted-foreground hover:text-foreground hover:bg-accent"
                  }`}
                >
                  {f.label}
                  {(statusCounts[f.key] || 0) > 0 && (
                    <span className="ml-1 text-[10px] opacity-60">{statusCounts[f.key]}</span>
                  )}
                </button>
              ))}
            </div>
            <Button variant="xai" size="default" className="gap-2 self-start" onClick={() => setIsDialogOpen(true)}>
              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              New Project
            </Button>
          </div>

          {/* Project list */}
          <div className="space-y-2">
            {filteredAutomations.map((automation) => (
              <ProjectRow key={automation.id} automation={automation} />
            ))}
          </div>

          {filteredAutomations.length === 0 && (
            <div className="rounded-2xl border border-dashed p-20 text-center">
              <div className="mx-auto max-w-xs space-y-3">
                <h3 className="text-base font-semibold text-foreground">No projects yet</h3>
                <p className="text-sm text-muted-foreground">
                  Create your first project to start monitoring what your users want.
                </p>
                <Button variant="xai" size="default" className="mt-4 gap-2" onClick={() => setIsDialogOpen(true)}>
                  New Project
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Dialog */}
      <Dialog open={isDialogOpen} onOpenChange={handleCloseDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>New Project</DialogTitle>
            <DialogDescription>Connect a GitHub repo and X account to start shipping.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Project name</label>
              <input type="text" value={newProjectName} onChange={(e) => setNewProjectName(e.target.value)} placeholder="My project"
                className="w-full rounded-lg border bg-background px-3 py-2.5 text-sm placeholder:text-muted-foreground focus:border-foreground focus:outline-none focus:ring-1 focus:ring-foreground" />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                <Github className="h-3.5 w-3.5" />
                GitHub repository
              </label>
              <input type="text" value={githubRepoUrl} onChange={(e) => setGithubRepoUrl(e.target.value)} placeholder="owner/repo"
                className="w-full rounded-lg border bg-background px-3 py-2.5 text-sm placeholder:text-muted-foreground focus:border-foreground focus:outline-none focus:ring-1 focus:ring-foreground" />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                <AtSign className="h-3.5 w-3.5" />
                X account
              </label>
              <input type="text" value={xAccountHandle} onChange={(e) => setXAccountHandle(e.target.value)} placeholder="@handle"
                className="w-full rounded-lg border bg-background px-3 py-2.5 text-sm placeholder:text-muted-foreground focus:border-foreground focus:outline-none focus:ring-1 focus:ring-foreground" />
            </div>
            <Button variant="xai" size="lg" className="w-full gap-2"
              disabled={!newProjectName.trim() || !githubRepoUrl.trim() || !xAccountHandle.trim() || isCreating}
              onClick={handleCreateProject}>
              {isCreating ? 'Creating...' : 'Create Project'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
