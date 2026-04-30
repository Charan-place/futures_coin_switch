"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Overview" },
  { href: "/positions", label: "Positions" },
  { href: "/trades", label: "Trades" },
];

export default function Navbar() {
  const path = usePathname();
  return (
    <nav
      style={{ background: "var(--surface)", borderBottom: "1px solid var(--border)" }}
      className="sticky top-0 z-10"
    >
      <div className="max-w-6xl mx-auto px-4 flex items-center gap-8 h-14">
        <span className="font-bold tracking-tight text-white text-sm">
          COIN SWITCH <span style={{ color: "var(--blue)" }}>FUTURES</span>
        </span>
        <div className="flex gap-1">
          {links.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className="px-3 py-1.5 rounded text-sm transition-colors"
              style={{
                color: path === href ? "white" : "var(--muted)",
                background: path === href ? "var(--border)" : "transparent",
              }}
            >
              {label}
            </Link>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span style={{ color: "var(--muted)" }} className="text-xs">
            LIVE
          </span>
        </div>
      </div>
    </nav>
  );
}
