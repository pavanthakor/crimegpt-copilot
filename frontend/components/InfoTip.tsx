"use client";

// Small reusable glossary tooltip. Renders an info icon that reveals a one-line
// plain-language definition on hover or keyboard focus. Self-contained and accessible
// (the trigger is a real <button>); place it next to an acronym's first appearance.
export function InfoTip({ term, text }: { term: string; text: string }) {
  return (
    <span className="relative inline-flex align-middle group">
      <button
        type="button"
        aria-label={term}
        className="inline-flex items-center rounded text-on-surface-variant hover:text-primary focus:text-primary focus:outline-none focus-visible:ring-1 focus-visible:ring-primary"
      >
        <span className="material-symbols-outlined text-[15px] leading-none">info</span>
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 bottom-full z-50 mb-1.5 w-56 -translate-x-1/2 rounded bg-inverse-surface px-3 py-2 text-left text-inverse-on-surface opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
      >
        <span className="block font-label-caps text-[10px] mb-0.5">{term}</span>
        <span className="block font-body-md text-[11px] leading-snug">{text}</span>
      </span>
    </span>
  );
}
