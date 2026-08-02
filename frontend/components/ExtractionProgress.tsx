"use client";
import { useEffect, useRef, useState } from "react";

import { useI18n, type TKey } from "@/lib/i18n";
import {
  SLOW_AFTER_MS,
  percentFor,
  secondsFor,
  stageFor,
} from "@/lib/extractionProgress";

/**
 * The wait while intake extraction runs.
 *
 * Extraction genuinely takes 12-40s on the local 7B and this does not make it faster. It
 * replaces a motionless spinner with something that shows the wait is progressing: what
 * the system is working on, how long it has been, and a bar that moves.
 *
 * WHY THIS RATHER THAN STREAMING FIELDS IN. Extraction is one non-streaming call
 * (`"stream": False`), and more importantly every entity it returns is PROVISIONAL until
 * the whole-response guards have run: grounding removes a person whose name is not
 * traceable to the officer's words, dedupe drops repeats, and the junk guard can discard
 * the entire result and hand back an empty draft. Painting a person into the record as it
 * arrives would show the officer a name the guards are about to delete — surfacing
 * exactly the invented data the guards exist to suppress. The draft appears when it is
 * true, not while it is still a guess.
 *
 * WHAT IS HONEST HERE. The elapsed seconds are real. The bar is paced by elapsed time
 * against a measured median and CANNOT REACH 100% on its own — only the response
 * completes it, so the officer is never told the work is finished before it is. The stage
 * labels describe the phases the request actually goes through, in the order the backend
 * performs them (the narrative is read, people and property are picked out, then every
 * value is checked back against the officer's own words). They are paced by typical
 * timings rather than reported by the server, which is why the last stage is open-ended:
 * a slow run rests on "checking" instead of a bar that fills and then waits.
 */

export default function ExtractionProgress({ active }: { active: boolean }) {
  const { t } = useI18n();
  const [elapsed, setElapsed] = useState(0);
  const startedAt = useRef<number>(0);

  useEffect(() => {
    if (!active) {
      setElapsed(0);
      return;
    }
    startedAt.current = Date.now();
    setElapsed(0);
    const id = window.setInterval(() => setElapsed(Date.now() - startedAt.current), 200);
    return () => window.clearInterval(id);
  }, [active]);

  if (!active) return null;

  const stage = stageFor(elapsed);
  const percent = percentFor(elapsed);
  const seconds = secondsFor(elapsed);

  return (
    <div role="status" aria-live="polite" className="space-y-2">
      <p className="font-body-md text-on-surface flex items-center gap-2">
        <span className="material-symbols-outlined animate-spin text-lg text-primary">
          progress_activity
        </span>
        {t(`intake.progress.${stage}` as TKey)}
        <span className="font-mono-sm text-on-surface-variant ml-1">
          {t("intake.progress.elapsed", { sec: seconds })}
        </span>
      </p>

      <div className="h-1 w-full bg-surface-container-low rounded overflow-hidden">
        <div
          className="h-full bg-primary transition-[width] duration-200 ease-linear"
          style={{ width: `${percent}%` }}
        />
      </div>

      {elapsed >= SLOW_AFTER_MS && (
        <p className="font-body-sm text-on-surface-variant">{t("intake.progress.slow")}</p>
      )}
    </div>
  );
}
