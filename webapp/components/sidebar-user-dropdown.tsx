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

interface SidebarUserDropdownProps {
  user: User;
}

export function SidebarUserDropdown({ user }: SidebarUserDropdownProps) {
  const router = useRouter();

  const handleLogout = async () => {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/auth/login");
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="sidebar-expanded-only flex w-full items-center gap-2.5 rounded-lg bg-secondary/50 p-2.5 transition-colors hover:bg-secondary cursor-pointer">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/20">
            <span className="text-xs font-medium text-primary">
              {user.email?.charAt(0).toUpperCase()}
            </span>
          </div>
          <div className="flex-1 min-w-0 text-left">
            <p className="text-xs font-medium text-foreground truncate">
              {user.email?.split('@')[0]}
            </p>
            <p className="text-[10px] text-muted-foreground truncate">{user.email}</p>
          </div>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuItem onClick={handleLogout} className="cursor-pointer">
          <LogOut className="mr-2 h-4 w-4" />
          <span>Logout</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

