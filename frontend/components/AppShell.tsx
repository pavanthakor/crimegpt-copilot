"use client";
import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import { useAuth } from "./AuthProvider";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";

/**
 * Applies the app shell (sidebar + top bar + content area) around page content.
 * Pre-auth screens (login) and the pre-hydration state render bare, so the login
 * page keeps working exactly as before and there is no chrome flash.
 */
export default function AppShell({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth();
  const pathname = usePathname() ?? "";

  const showChrome = ready && !!user && pathname !== "/login";

  if (!showChrome) {
    return <>{children}</>;
  }

  return (
    <div className="min-h-screen bg-background text-on-background">
      <Sidebar />
      <TopBar />
      <main className="ml-[280px] pt-16 min-h-screen custom-scrollbar">
        <div className="px-edge-margin py-stack-lg">{children}</div>
      </main>
    </div>
  );
}
