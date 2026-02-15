'use server';

import { createClient } from "@/lib/supabase/server";
import { revalidatePath } from "next/cache";

export async function monitorTweet(formData: FormData) {
  const supabase = await createClient();
  const tweetUrl = formData.get("tweetUrl") as string;

  if (!tweetUrl) {
    return { error: "Tweet URL is required" };
  }

  const { error } = await supabase
    .from("pending_tweets")
    .insert({ tweet_url: tweetUrl });

  if (error) {
    console.error("Error inserting pending tweet:", error);
    return { error: error.message };
  }

  revalidatePath("/features");
  return { success: true };
}

export async function createPlan(automationId: string) {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
  const supabase = await createClient();

  try {
    // Check if this is a pending_tweet or a tweet
    const { data: pendingTweet } = await supabase
      .from("pending_tweets")
      .select("*")
      .eq("id", automationId)
      .single();

    if (pendingTweet) {
      // For pending tweets, we might need to process them first
      // But they need to be in the tweets table first
      return { error: "Pending tweets need to be processed first. Please wait for processing." };
    }

    // Check if it's a tweet
    const { data: tweet } = await supabase
      .from("tweets")
      .select("*")
      .eq("id", automationId)
      .single();

    if (!tweet) {
      return { error: "Tweet not found" };
    }

    // Check if tweet has a feature_ticket_id
    if (!tweet.feature_ticket_id) {
      // Process the tweet first to create a ticket
      const processResponse = await fetch(`${backendUrl}/api/tweets/process`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ tweet_id: tweet.id }),
      });

      if (!processResponse.ok) {
        const errorData = await processResponse.json();
        return { error: errorData.error || "Failed to process tweet" };
      }

      const processResult = await processResponse.json();
      const ticketId = processResult.ticket_id;

      // Now generate the plan
      const planResponse = await fetch(`${backendUrl}/api/tickets/${ticketId}/generate-plan`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!planResponse.ok) {
        const errorData = await planResponse.json();
        return { error: errorData.error || "Failed to generate plan" };
      }

      const planResult = await planResponse.json();
      revalidatePath(`/automations/${automationId}`);
      return { success: true, planId: planResult.plan_id };
    }

    // Tweet already has a ticket, generate plan directly
    const planResponse = await fetch(`${backendUrl}/api/tickets/${tweet.feature_ticket_id}/generate-plan`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!planResponse.ok) {
      const errorData = await planResponse.json();
      return { error: errorData.error || "Failed to generate plan" };
    }

    const planResult = await planResponse.json();
    revalidatePath(`/automations/${automationId}`);
    return { success: true, planId: planResult.plan_id };
  } catch (error) {
    console.error("Error creating plan:", error);
    return { error: error instanceof Error ? error.message : "An error occurred" };
  }
}

export async function updateProjectStatus(projectId: string, status: string) {
  const supabase = await createClient();

  const { error } = await supabase
    .from("projects")
    .update({ status })
    .eq("id", projectId);

  if (error) {
    console.error("Error updating project status:", error);
    return { error: error.message };
  }

  revalidatePath(`/features/${projectId}`);
  revalidatePath("/features");
  return { success: true };
}

export async function startBuild(projectId: string) {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

  try {
    const response = await fetch(`${backendUrl}/api/projects/${projectId}/approve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ auto_generate_plan: true }),
    });

    const data = await response.json();

    if (!response.ok) {
      return { error: data?.error || "Failed to create GitHub issue" };
    }

    revalidatePath(`/features/${projectId}`);
    revalidatePath("/features");

    return {
      success: true,
      issueUrl: data.github_issue_url,
      issueNumber: data.github_issue_number,
    };
  } catch (error) {
    console.error("Error starting build:", error);
    return { error: error instanceof Error ? error.message : "An error occurred" };
  }
}

export async function approvePlan(planId: string, content: string) {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

  try {
    const response = await fetch(`${backendUrl}/api/plans/${planId}/approve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ content }),
    });

    const data = await response.json();

    if (!response.ok) {
      return { error: data?.error || "Failed to approve plan" };
    }

    const projectId = data?.plan?.project_id;
    if (projectId) {
      revalidatePath(`/features/${projectId}`);
    }
    revalidatePath("/features");

    return { success: true, projectId };
  } catch (error) {
    console.error("Error approving plan:", error);
    return { error: error instanceof Error ? error.message : "An error occurred" };
  }
}
