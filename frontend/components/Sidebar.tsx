"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = {
  label: string;
  href: string;
  icon: string; // Material Symbols ligature name
  ready: boolean; // false → page not built yet, shown muted + non-clickable
};

// Dashboard · Cases · Evidence · Documents · AI Analysis · Audit.
// Only pages that exist are enabled; the rest are muted so nothing 404s during a
// demo. Flip `ready` to true as each page ships.
//
// Evidence and Documents have no standalone page — they live as tabs inside a
// case. `caseTab` deep-links them to the current case's tab when one is open,
// otherwise they fall back to the case list (where an officer picks a case).
type Item = NavItem & { caseTab?: string };
const NAV: Item[] = [
  { label: "Dashboard", href: "/dashboard", icon: "dashboard", ready: true },
  { label: "Cases", href: "/cases", icon: "folder_shared", ready: true },
  { label: "Evidence", href: "/cases", icon: "inventory_2", ready: true, caseTab: "evidence" },
  { label: "Documents", href: "/cases", icon: "description", ready: true, caseTab: "documents" },
  { label: "AI Analysis", href: "/analysis", icon: "neurology", ready: true },
  { label: "Audit", href: "/audit", icon: "verified_user", ready: true },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/dashboard") return pathname === "/dashboard";
  return pathname === href || pathname.startsWith(href + "/");
}

// A /cases/{id} pathname if we're inside a case workspace, else null.
function currentCasePath(pathname: string): string | null {
  const m = pathname.match(/^\/cases\/\d+/);
  return m ? m[0] : null;
}

export default function Sidebar() {
  const pathname = usePathname() ?? "";
  const casePath = currentCasePath(pathname);

  return (
    <nav className="fixed left-0 top-0 h-full w-[280px] flex flex-col py-stack-lg bg-surface border-r border-outline-variant z-50">
      {/* Branding — CrimeGPT (not NIA, not Govt of India) */}
      <div className="px-6 mb-10 flex items-center gap-3">
        <div className="w-10 h-10 bg-primary flex items-center justify-center">
          <span className="material-symbols-outlined filled text-white">security</span>
        </div>
        <div>
          <h1 className="font-display-case text-headline-md leading-tight text-primary">
            CrimeGPT
          </h1>
          <p className="font-label-caps text-[10px] tracking-widest text-on-surface-variant">
            Investigative Intelligence
          </p>
        </div>
      </div>

      <div className="px-4 space-y-1 flex-grow">
        {NAV.map((item) => {
          // Case-tab shortcuts deep-link into the open case (else to the case list);
          // they are jump-links, so the active highlight stays on "Cases".
          const href = item.caseTab
            ? casePath
              ? `${casePath}?tab=${item.caseTab}`
              : "/cases"
            : item.href;
          const active = item.caseTab ? false : isActive(pathname, item.href);

          if (!item.ready) {
            // Muted, non-interactive placeholder with a "Soon" tag.
            return (
              <div
                key={item.label}
                aria-disabled="true"
                title="Coming soon"
                className="flex items-center gap-4 px-4 py-3 rounded text-outline/60 cursor-not-allowed select-none"
              >
                <span className="material-symbols-outlined">{item.icon}</span>
                <span className="font-body-md">{item.label}</span>
                <span className="ml-auto font-label-caps text-[9px] text-outline/60 border border-outline-variant rounded px-1 py-0.5">
                  Soon
                </span>
              </div>
            );
          }

          return (
            <Link
              key={item.label}
              href={href}
              className={
                active
                  ? "flex items-center gap-4 px-4 py-3 bg-surface-container-high text-primary font-bold border-r-4 border-primary transition-all duration-100"
                  : "flex items-center gap-4 px-4 py-3 rounded text-on-surface-variant hover:bg-surface-container-low transition-colors"
              }
              aria-current={active ? "page" : undefined}
            >
              <span
                className={active ? "material-symbols-outlined filled" : "material-symbols-outlined"}
              >
                {item.icon}
              </span>
              <span className="font-body-md">{item.label}</span>
            </Link>
          );
        })}
      </div>

      <div className="px-6 pt-4 mt-4 border-t border-outline-variant">
        <p className="font-label-caps text-[10px] text-on-surface-variant">Ahmedabad City Police</p>
        <p className="font-mono-sm text-outline">Cyber Crime Branch</p>
      </div>
    </nav>
  );
}
