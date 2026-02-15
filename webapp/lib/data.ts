import { createClient } from "@/lib/supabase/server";
import { Automation } from "@/components/dashboard-content";
import { MonitoringItem } from "@/components/sidebar";

export async function getMonitorings(): Promise<MonitoringItem[]> {
  const supabase = await createClient();
  
  // Fetch projects to show in sidebar
  const { data: projects, error } = await supabase
    .from("projects")
    .select("*")
    .order("created_at", { ascending: false });

  if (error) {
    console.error("Error fetching projects:", error);
    return [];
  }

  if (!projects || projects.length === 0) {
    return [];
  }

  return projects.map((project: any) => ({
    id: project.id,
    title: project.title || 'Untitled Project',
    status: (project.status === 'pending' ? 'pending' : 
             project.status === 'completed' ? 'completed' : 
             project.status === 'failed' ? 'failed' :
             project.status === 'planning' || project.status === 'executing' ? 'active' : 'paused') as any,
    type: 'tweet' as const,
  }));
}

export async function getAutomations(): Promise<Automation[]> {
  const supabase = await createClient();
  const { data: projects, error: projectError } = await supabase
    .from("projects")
    .select("*")
    .order("created_at", { ascending: false });

  if (projectError) {
    console.error("Error fetching projects:", projectError);
    return [];
  }

  if (!projects || projects.length === 0) {
    return [];
  }

  const repoConfigIds = projects.map((p: any) => p.repo_config_id).filter(Boolean);
  const uniqueRepoIds = Array.from(new Set(repoConfigIds));

  let repoConfigsById: Record<string, any> = {};
  if (uniqueRepoIds.length > 0) {
    const { data: repoConfigs, error: repoError } = await supabase
      .from("repo_configs")
      .select("*")
      .in("id", uniqueRepoIds);

    if (repoError) {
      console.error("Error fetching repo configs for projects:", repoError);
    } else if (repoConfigs) {
      repoConfigsById = repoConfigs.reduce((acc: Record<string, any>, repo: any) => {
        acc[repo.id] = repo;
        return acc;
      }, {});
    }
  }

  const projectIds = projects.map((p: any) => p.id);
  let tweetsByProject: Record<string, any[]> = {};

  if (projectIds.length > 0) {
    const { data: tweets, error: tweetsError } = await supabase
      .from("tweets")
      .select("*")
      .in("project_id", projectIds);

    if (tweetsError) {
      console.error("Error fetching tweets for projects:", tweetsError);
    } else if (tweets) {
      tweetsByProject = tweets.reduce((acc: Record<string, any[]>, tweet: any) => {
        if (!acc[tweet.project_id]) acc[tweet.project_id] = [];
        acc[tweet.project_id].push(tweet);
        return acc;
      }, {});
    }
  }

  const mapStatus = (status: string): Automation["status"] => {
    if (["planning", "provisioning", "executing"].includes(status)) return "active";
    if (status === "pending") return "pending";
    if (status === "failed") return "failed";
    if (status === "completed") return "completed";
    if (status === "closed") return "paused";
    return "draft";
  };

  return projects.map((project: any) => {
    const repo = project.repo_config_id ? repoConfigsById[project.repo_config_id] : null;
    const projectTweets = tweetsByProject[project.id] || [];

    const engagement = projectTweets.length
      ? {
          likes: projectTweets.reduce((sum: number, t: any) => sum + (t.likes_count || 0), 0),
          retweets: projectTweets.reduce((sum: number, t: any) => sum + (t.retweets_count || 0), 0),
          replies: projectTweets.reduce((sum: number, t: any) => sum + (t.replies_count || 0), 0),
          total: projectTweets.reduce(
            (sum: number, t: any) =>
              sum + (t.likes_count || 0) + (t.retweets_count || 0) + (t.replies_count || 0),
            0
          ),
        }
      : { likes: 0, retweets: 0, replies: 0, total: 0 };

    const description =
      project.description ||
      (repo
        ? `Monitoring ${repo.x_account_handle} for ${repo.github_owner}/${repo.github_repo}`
        : "Automation");

    return {
      id: project.id,
      name: project.title || "Untitled Project",
      description,
      trigger: "New tweet",
      action: "Process",
      status: mapStatus(project.status),
      runsToday: 0,
      lastRun: project.updated_at,
      engagement,
      tweetCount: projectTweets.length,
    };
  });
}

export interface TweetDetail {
  id: string;
  tweet_id: string;
  tweet_text: string;
  tweet_author_username: string;
  tweet_created_at: string;
  likes_count: number;
  retweets_count: number;
  replies_count: number;
  processed: boolean;
  sentiment_score: number | null;
}

export async function getAutomationDetails(automationId: string) {
  const supabase = await createClient();

  // Try to get from projects table first
  const { data: project } = await supabase
    .from("projects")
    .select("*")
    .eq("id", automationId)
    .single();

  if (project) {
    // If project has a plan, load it
    let plan = null;
    if (project.plan_id) {
      const { data: planRow } = await supabase
        .from("plans")
        .select("*")
        .eq("id", project.plan_id)
        .single();
      plan = planRow || null;
    }

    // Get related tweets for this project
    const { data: relatedTweets } = await supabase
      .from("tweets")
      .select("*")
      .eq("project_id", automationId)
      .order("created_at", { ascending: false });

    const totalEngagement = {
      likes: relatedTweets?.reduce((sum: number, t: any) => sum + (t.likes_count || 0), 0) || 0,
      retweets: relatedTweets?.reduce((sum: number, t: any) => sum + (t.retweets_count || 0), 0) || 0,
      replies: relatedTweets?.reduce((sum: number, t: any) => sum + (t.replies_count || 0), 0) || 0,
    };

    return {
      tweet: null,
      project,
      relatedTweets: relatedTweets || [],
      totalEngagement,
      plan,
      issueUrl: project.github_issue_url,
      issueNumber: project.github_issue_number,
    };
  }

  // Try to get from tweets table
  const { data: tweet } = await supabase
    .from("tweets")
    .select("*")
    .eq("id", automationId)
    .single();

  if (tweet) {
    // Get ALL tweets and filter for related ones
    const { data: allTweets } = await supabase
      .from("tweets")
      .select("*")
      .order("created_at", { ascending: false });

    // Extract keywords from the main tweet
    const keywords = tweet.tweet_text.toLowerCase().split(' ').filter((w: string) => w.length > 3);

    // Find all related tweets (including the main tweet)
    const relatedTweets = allTweets?.filter((t: any) => {
      if (t.id === automationId) return false; // Exclude the main tweet from related list
      const tweetTextLower = t.tweet_text?.toLowerCase() || '';
      return keywords.some((k: string) => tweetTextLower.includes(k));
    }) || [];

    // Calculate engagement including the main tweet
    const allRelatedIncludingMain = [tweet, ...relatedTweets];
    const totalEngagement = {
      likes: allRelatedIncludingMain.reduce((sum: number, t: any) => sum + (t.likes_count || 0), 0),
      retweets: allRelatedIncludingMain.reduce((sum: number, t: any) => sum + (t.retweets_count || 0), 0),
      replies: allRelatedIncludingMain.reduce((sum: number, t: any) => sum + (t.replies_count || 0), 0),
    };

    return {
      tweet,
      relatedTweets,
      totalEngagement,
    };
  }

  // Try pending_tweets
  const { data: pendingTweet } = await supabase
    .from("pending_tweets")
    .select("*")
    .eq("id", automationId)
    .single();

  if (pendingTweet) {
    return {
      pendingTweet,
      relatedTweets: [],
      totalEngagement: {
        likes: 0,
        retweets: 0,
        replies: 0,
      }
    };
  }

  return null;
}

export interface TickerTweet {
  id: string;
  tweet_text: string;
  tweet_author_username: string;
  likes_count: number;
  retweets_count: number;
  replies_count: number;
  tweet_created_at: string;
}

export async function getRecentTweets(limit: number = 20): Promise<TickerTweet[]> {
  const supabase = await createClient();

  const { data: tweets, error } = await supabase
    .from("tweets")
    .select("id, tweet_text, tweet_author_username, likes_count, retweets_count, replies_count, tweet_created_at")
    .order("created_at", { ascending: false })
    .limit(limit);

  if (error) {
    console.error("Error fetching recent tweets:", error);
    return [];
  }

  return tweets || [];
}
