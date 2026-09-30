import type { CourseRun, RunInput, RunStatus, RunStep } from "../api/types";
import { RUN_STEPS } from "../api/types";

/**
 * The 7-step workflow is a UI concept; the backend only stores RunStatus
 * (planned|announced|open|running|completed|cancelled). We derive the step from data:
 *   planned   -> plan (no enrollments) | candidates (some enrolled)
 *   announced -> announce | motivations (once a motivation is confirmed)
 *   open      -> institute letter stage
 *   running   -> settlement (invoice/payment) stage
 *   completed -> settlement until payment has started, then level 3
 *   cancelled -> no step (returned as null)
 */
export function deriveStep(r: Pick<CourseRun, "status" | "enrollment_count" | "motivation_yes_count" | "payment_started"> & { workflow?: CourseRun["workflow"] }): RunStep | null {
  if (r.status === "cancelled") return null;
  const w = r.workflow;
  if (w) { // authoritative: backend-derived flags (GET /runs/{id})
    if (!w.announced) return r.enrollment_count > 0 ? "candidates" : "plan";
    if (!w.motivations_collected) return "motivations";
    if (!w.institute_letter_sent) return "institute_letter";
    if (!(w.settlement_sent || w.invoice_received)) return "settlement";
    return "level3";
  }
  switch (r.status) { // fallback for list items without `workflow`
    case "planned": return r.enrollment_count > 0 ? "candidates" : "plan";
    case "announced": return r.motivation_yes_count > 0 ? "motivations" : "announce";
    case "open": return "institute_letter";
    case "running": return "settlement";
    case "completed": return r.payment_started ? "level3" : "settlement";
  }
}
/** What to PATCH when the user finishes `step`; null when the next step is derived automatically. */
export function advancePatch(step: RunStep, run: Pick<CourseRun, "status">): RunInput | null {
  switch (step) {
    case "candidates": return { status: "announced" };
    case "motivations": return { status: "open" };
    case "institute_letter": return { status: "running" };
    case "settlement": return run.status === "running" ? { status: "completed" } : { payment_process: "started" };
    default: return null;
  }
}
export const advanceStatus = (step: RunStep, run: Pick<CourseRun, "status"> = { status: "planned" }): RunStatus | null => advancePatch(step, run)?.status ?? null;
export const stepIndex = (s: RunStep | null) => (s ? RUN_STEPS.indexOf(s) : RUN_STEPS.length);
