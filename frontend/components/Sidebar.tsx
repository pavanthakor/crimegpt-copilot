"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = {
  label: string;
  href: string;
  icon: string; // Material Symbols ligature name
};

// Dashboard · Cases · Evidence · Documents · AI Analysis · Audit
const NAV: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: "dashboard" },
  { label: "Cases", href: "/cases", icon: "folder_shared" },
  { label: "Evidence", href: "/evidence", icon: "inventory_2" },
  { label: "Documents", href: "/documents", icon: "description" },
  { label: "AI Analysis", href: "/analysis", icon: "neurology" },
  { label: "Audit", href: "/audit", icon: "verified_user" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/dashboard") return pathname === "/dashboard";
  return pathname === href || pathname.startsWith(href + "/");
}

export default function Sidebar() {
  const pathname = usePathname() ?? "";

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
          const active = isActive(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
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
