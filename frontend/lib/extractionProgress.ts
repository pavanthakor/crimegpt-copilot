/**
 * How the intake-extraction wait is paced.
 *
 * The decision lives here as pure functions, separate from the React component that
 * watches the clock, so the pacing can be tested directly rather than by sampling a
 * running browser. Nothing here touches the DOM or the network — it maps elapsed
 * milliseconds onto "what to say" and "how full the bar is".
 */

/** Measured: ~12-15s for an English narrative, ~22-27s for Gujarati on the local 7B. */
export const EXPECTED_MS = 22000;

/** Past this, say plainly that it is still working rather than let a near-full bar imply a stall. */
export const SLOW_AFTER_MS = 45000;

/** The bar starts here and stops short of the end — the response owns the last 5%. */
export const START_PERCENT = 6;
export const MAX_PERCENT = 95;

export type StageKey = "reading" | "people" | "items" | "checking";

/**
 * The phases a single extraction goes through, in the order the backend performs them:
 * the narrative is read, people and property are picked out, then every value is checked
 * back against the officer's own words (the grounding pass).
 *
 * `untilMs` is when the NEXT phase takes over. The last is open-ended on purpose: a slow
 * run should rest on "checking" rather than run out of stages.
 */
const STAGES: { key: StageKey; untilMs: number }[] = [
  { key: "reading", untilMs: 4000 },
  { key: "people", untilMs: 12000 },
  { key: "items", untilMs: 19000 },
  { key: "checking", untilMs: Number.POSITIVE_INFINITY },
];

export function stageFor(elapsedMs: number): StageKey {
  return (STAGES.find((s) => elapsedMs < s.untilMs) ?? STAGES[STAGES.length - 1]).key;
}

/**
 * How full the bar is. CANNOT REACH 100 however long it runs — only the arriving
 * response completes it, so the officer is never shown a finished bar over unfinished
 * work.
 */
export function percentFor(elapsedMs: number): number {
  const frac = Math.min(Math.max(elapsedMs, 0) / EXPECTED_MS, 1);
  return START_PERCENT + Math.round(frac * (MAX_PERCENT - START_PERCENT));
}

/** Whole elapsed seconds, for the counter beside the label. */
export function secondsFor(elapsedMs: number): number {
  return Math.floor(Math.max(elapsedMs, 0) / 1000);
}
