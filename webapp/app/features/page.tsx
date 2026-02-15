import { SidebarLayout } from "@/components/sidebar";
import { SidebarUser } from "@/components/sidebar-user";
import { DashboardContent } from "@/components/dashboard-content";
import { Suspense } from "react";
import { getAutomations, getMonitorings, getRecentTweets } from "@/lib/data";

type AutomationsPageProps = {
  searchParams: Promise<{ new?: string }>;
};

async function FeaturesContent({ searchParams }: { searchParams: Promise<{ new?: string }> }) {
  const resolvedSearchParams = await searchParams;
  const shouldOpenDialog = resolvedSearchParams?.new === "1";

  const [monitorings, automations, recentTweets] = await Promise.all([
    getMonitorings(),
    getAutomations(),
    getRecentTweets(20)
  ]);

  return (
    <SidebarLayout userSection={<Suspense><SidebarUser /></Suspense>} monitorings={monitorings}>
      <DashboardContent initialDialogOpen={shouldOpenDialog} automations={automations} recentTweets={recentTweets} />
    </SidebarLayout>
  );
}

export default async function AutomationsPage({ searchParams }: AutomationsPageProps) {
  return (
    <Suspense fallback={
      <SidebarLayout userSection={<Suspense><SidebarUser /></Suspense>} monitorings={[]}>
        <div className="flex items-center justify-center min-h-screen">
          <div className="text-muted-foreground">Loading...</div>
        </div>
      </SidebarLayout>
    }>
      <FeaturesContent searchParams={searchParams} />
    </Suspense>
  );
}
