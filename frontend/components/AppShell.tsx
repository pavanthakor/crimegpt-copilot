"use client";
import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import { useAuth } from "./AuthProvider";
import IdleLogout from "./IdleLogout";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";

/**
 * Applies the app shell (sidebar + top bar + content area) around page content.
 * Pre-auth screens (login) and the pre-hydration state render bare, so the login
 * page keeps working exactly as before and there is no chrome flash.
 *
 * The mobile field page (/m) renders bare too, for a different reason: it is a
 * phone-sized page and this chrome is a 280px sidebar. It brings its own header, its own
 * language switcher and its own idle watchdog. Every desktop route is unaffected.
 */
export default function AppShell({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth();
  const pathname = usePathname() ?? "";

  const bareRoute = pathname === "/login" || pathname === "/m" || pathname.startsWith("/m/");
  const showChrome = ready && !!user && !bareRoute;

  if (!showChrome) {
    return <>{children}</>;
  }

  return (
    <div className="min-h-screen bg-background text-on-background">
      {/* Mounted with the chrome, so it watches only signed-in sessions and never the
          login screen. Renders nothing until it has something to warn about. */}
      <IdleLogout />
      <Sidebar />
      <TopBar />
      <main className="ml-[280px] pt-16 min-h-screen custom-scrollbar">
        <div className="px-edge-margin py-stack-lg">{children}</div>
      </main>
    </div>
  );
}
