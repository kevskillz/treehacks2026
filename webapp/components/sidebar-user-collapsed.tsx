"use client";

import { User } from "@supabase/supabase-js";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";

interface SidebarUserCollapsedProps {
  user: User;
}

export function SidebarUserCollapsed({ user }: SidebarUserCollapsedProps) {
  const router = useRouter();

  const handleLogout = async () => {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/auth/login");
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="sidebar-collapsed-only flex h-9 w-9 items-center justify-center rounded-full bg-primary/20 mx-auto transition-colors hover:bg-primary/30 cursor-pointer"
          title={user.email || "User"}
        >
          <span className="text-sm font-medium text-primary">
            {user.email?.charAt(0).toUpperCase()}
          </span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" side="right" className="w-56">
        <div className="px-2 py-1.5 text-sm">
          <p className="font-medium truncate">{user.email?.split('@')[0]}</p>
          <p className="text-xs text-muted-foreground truncate">{user.email}</p>
        </div>
        <DropdownMenuItem onClick={handleLogout} className="cursor-pointer">
          <LogOut className="mr-2 h-4 w-4" />
          <span>Logout</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
