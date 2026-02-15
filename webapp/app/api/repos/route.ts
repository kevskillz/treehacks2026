import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

const requirePositiveString = (value?: string): value is string => {
  return typeof value === "string" && value.trim().length > 0;
};

const normalizeHandle = (value: string | undefined) => {
  if (!requirePositiveString(value)) return undefined;
  return value.trim().startsWith("@") ? value.trim() : `@${value.trim()}`;
};

export async function GET() {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("repo_configs")
    .select("*")
    .order("created_at", { ascending: false });

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ repo_configs: data ?? [] });
}

export async function POST(req: NextRequest) {
  const payload = await req.json();
  const {
    github_owner,
    github_repo,
    github_branch,
    x_account_handle,
    x_keywords,
    local_agent_enabled,
    auto_create_issues,
    auto_create_prs,
    project_title,
    project_description,
  } = payload;

  const supabase = await createClient();
  const { data: userData } = await supabase.auth.getUser();
  const userId = userData?.user?.id ?? null;

  const resolvedHandle = normalizeHandle(x_account_handle);
  const resolvedOwner = requirePositiveString(github_owner) ? github_owner.trim() : undefined;
  const resolvedRepo = requirePositiveString(github_repo) ? github_repo.trim() : undefined;
  const resolvedBranch = github_branch?.trim() || "main";

  // Pull account defaults if any fields are missing
  let defaultAccount: any = null;
  if (userId) {
    const { data: accountData } = await supabase
      .from("accounts")
      .select("*")
      .eq("id", userId)
      .maybeSingle();
    defaultAccount = accountData;
  }

  const finalOwner = resolvedOwner ?? defaultAccount?.github_owner;
  const finalRepo = resolvedRepo ?? defaultAccount?.github_repo;
  const finalHandle = resolvedHandle ?? defaultAccount?.x_account_handle;

  if (!requirePositiveString(finalOwner) || !requirePositiveString(finalRepo) || !requirePositiveString(finalHandle) || !requirePositiveString(project_title)) {
    return NextResponse.json(
      { error: "github_owner, github_repo, x_account_handle, and project_title are required" },
      { status: 400 }
    );
  }

  let repoConfigId = defaultAccount?.default_repo_config_id ?? null;

  // Create a repo_config if none exists or the payload overrides defaults
  if (!repoConfigId || resolvedOwner || resolvedRepo || resolvedHandle) {
    const { data, error } = await supabase
      .from("repo_configs")
      .insert({
        github_owner: finalOwner.trim(),
        github_repo: finalRepo.trim(),
        github_branch: resolvedBranch,
        x_account_handle: finalHandle.trim(),
        x_keywords: Array.isArray(x_keywords) ? x_keywords : [],
        local_agent_enabled: !!local_agent_enabled,
        auto_create_issues: !!auto_create_issues,
        auto_create_prs: !!auto_create_prs,
        user_id: userId ?? null,
      })
      .select()
      .single();

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    repoConfigId = data.id;

    // If we created a new repo config and the account exists, set it as default
    if (userId && defaultAccount) {
      await supabase
        .from("accounts")
        .update({
          default_repo_config_id: repoConfigId,
          github_owner: finalOwner.trim(),
          github_repo: finalRepo.trim(),
          github_branch: resolvedBranch,
          x_account_handle: finalHandle.trim(),
        })
        .eq("id", userId);
    }
  }

  if (!repoConfigId) {
    return NextResponse.json({ error: "Unable to resolve a repository configuration" }, { status: 500 });
  }

  const { data: projectData, error: projectError } = await supabase
    .from("projects")
    .insert({
      title: project_title.trim(),
      description:
        project_description?.trim() ||
        `Monitoring ${finalHandle.trim()} for ${finalOwner.trim()}/${finalRepo.trim()}`,
      ticket_type: "feature",
      status: "pending",
      repo_config_id: repoConfigId,
    })
    .select()
    .single();

  if (projectError) {
    return NextResponse.json({ error: projectError.message }, { status: 500 });
  }

  return NextResponse.json({ repo_config: data, project: projectData }, { status: 201 });
}

