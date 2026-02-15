import { SidebarLayout } from "@/components/sidebar";
import { SidebarUser } from "@/components/sidebar-user";
import { Suspense } from "react";
import { getAutomations, getMonitorings, getAutomationDetails } from "@/lib/data";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { ProjectDetail } from "@/components/project-detail";

type ProjectPageProps = {
  params: Promise<{ id: string }>;
};

export default async function ProjectPage({ params }: ProjectPageProps) {
  const { id } = await params;
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
  const [monitorings, automations, details] = await Promise.all([
    getMonitorings(),
    getAutomations(),
    getAutomationDetails(id)
  ]);

  if (!details) {
    return (
      <SidebarLayout userSection={<Suspense><SidebarUser /></Suspense>} monitorings={monitorings}>
        <div className="min-h-screen p-8 lg:p-16">
          <div className="mx-auto max-w-4xl">
            <h1 className="text-2xl font-medium text-foreground mb-4">Feature not found</h1>
            <Link href="/features">
              <Button variant="xai">Back to Features</Button>
            </Link>
          </div>
        </div>
      </SidebarLayout>
    );
  }

  const { project, relatedTweets, issueUrl, issueNumber, plan } = details as any;
  const automationData = automations.find(a => a.id === id);

  // Use project data as primary, fall back to automation data
  const displayName = project?.title || automationData?.name || 'Untitled Feature';
  const displayDescription = project?.description || automationData?.description || '';
  const displayStatus = project?.status || automationData?.status || 'pending';
  const displayTrigger = automationData?.trigger || 'Tweet cluster';
  const displayAction = automationData?.action || 'Create GitHub issue';
  const repoText = automationData?.description || '';
  const repoMatch = repoText.match(/for\s+([^\s]+\/[^\s]+)/);
  const handleMatch = repoText.match(/Monitoring\s+(@?\w+)/);
  const displayRepo = repoMatch?.[1];
  const displayHandle = handleMatch?.[1];
  const hasIssue = Boolean(issueUrl || project?.github_issue_url);

  return (
    <SidebarLayout userSection={<Suspense><SidebarUser /></Suspense>} monitorings={monitorings}>
      <ProjectDetail
        id={id}
        displayName={displayName}
        displayDescription={displayDescription}
        displayStatus={displayStatus}
        displayTrigger={displayTrigger}
        displayAction={displayAction}
        displayRepo={displayRepo}
        displayHandle={displayHandle}
        relatedTweets={relatedTweets || []}
        planId={project?.plan_id}
        planContent={plan?.content}
        projectStatus={project?.status || displayStatus}
        backendUrl={backendUrl}
        hasIssue={hasIssue}
        issueUrl={issueUrl || project?.github_issue_url}
        issueNumber={issueNumber || project?.github_issue_number}
      />
    </SidebarLayout>
  );
}
