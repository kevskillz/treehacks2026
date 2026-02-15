import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { SidebarUserDropdown } from "./sidebar-user-dropdown";
import { SidebarUserCollapsed } from "./sidebar-user-collapsed";

export async function SidebarUser() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();
  const user = data?.user;

  if (user) {
    return (
      <>
        <SidebarUserDropdown user={user} />
        <SidebarUserCollapsed user={user} />
      </>
    );
  }

  return (
    <>
      {/* Expanded state */}
      <Link
        href="/auth/login"
        className="sidebar-expanded-only flex items-center gap-2.5 rounded-lg bg-secondary/50 p-2.5 transition-colors hover:bg-secondary"
      >
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/20">
          <svg
            className="h-3.5 w-3.5 text-primary"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
            />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-foreground">Sign in</p>
          <p className="text-[10px] text-muted-foreground">Access your account</p>
        </div>
        <svg
          className="h-3.5 w-3.5 text-muted-foreground"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 5l7 7-7 7"
          />
        </svg>
      </Link>
      {/* Collapsed state */}
      <Link
        href="/auth/login"
        className="sidebar-collapsed-only flex h-9 w-9 items-center justify-center rounded-full bg-primary/20 mx-auto transition-colors hover:bg-primary/30"
        title="Sign in"
      >
        <svg
          className="h-4 w-4 text-primary"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
          />
        </svg>
      </Link>
    </>
  );
}
