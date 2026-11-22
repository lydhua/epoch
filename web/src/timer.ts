import type { Attempt } from "./api";

export type Draft = {
  version: 1;
  elapsed: number;
  started: number | null;
  measured: boolean;
  outcome: string;
  correction: string;
  confidence: string;
  pending: Attempt | null;
};
export const fresh = (): Draft => ({
  version: 1,
  elapsed: 0,
  started: null,
  measured: false,
  outcome: "independent",
  correction: "",
  confidence: "",
  pending: null,
});
export function elapsed(draft: Draft, now: number) {
  return (
    draft.elapsed +
    (draft.started === null ? 0 : Math.max(0, now - draft.started))
  );
}
export function pause(draft: Draft, now: number): Draft {
  return { ...draft, elapsed: elapsed(draft, now), started: null };
}
export function clockChanged(draft: Draft, now: number) {
  return (
    draft.started !== null &&
    (now < draft.started || now - draft.started > 12 * 3600000)
  );
}
export function loadDraft(key: string): Draft {
  const raw = localStorage.getItem(key);
  if (!raw) return fresh();
  const d = JSON.parse(raw) as Draft;
  if (
    d.version !== 1 ||
    !Number.isFinite(d.elapsed) ||
    d.elapsed < 0 ||
    !(d.started === null || Number.isFinite(d.started)) ||
    typeof d.measured !== "boolean" ||
    typeof d.outcome !== "string" ||
    typeof d.correction !== "string" ||
    typeof d.confidence !== "string" ||
    !(
      d.pending === null ||
      (typeof d.pending?.id === "string" &&
        typeof d.pending?.occurred_at === "string")
    )
  ) {
    throw new Error(
      "The saved draft could not be read. Clear this site’s local storage to start again.",
    );
  }
  return d;
}
export function duration(ms: number) {
  const seconds = Math.floor(ms / 1000);
  return `${Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
}
