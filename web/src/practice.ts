import type { Item, Receipt } from "./api";

export type PracticeEvent = { item: Item; receipt: Receipt };
export const outcomeName = (value: string) =>
  ({
    independent: "Independent",
    with_hints: "Used hints",
    consulted_solution: "Read solution",
    not_solved: "Not solved",
  })[value] || value;
export function minutes(seconds: number) {
  return `${Number((seconds / 60).toFixed(1))} min`;
}
export function timing(receipt?: Receipt) {
  const evidence = receipt?.attempt.timing;
  const seconds = evidence?.corrected_seconds ?? evidence?.measured_seconds;
  return seconds == null ? "Not timed" : minutes(seconds);
}
export function localDay(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}
export function date(value: string | null) {
  return value
    ? new Date(value).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
      })
    : "Unscheduled";
}
export function dueLabel(item: Item, now: number) {
  const due = item.schedule.decision.next_due_at;
  if (!due) return "Archived";
  const day = new Date(due);
  day.setHours(0, 0, 0, 0);
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  const days = Math.round((today.getTime() - day.getTime()) / 86400000);
  if (new Date(due).getTime() > now) return `Due ${date(due)}`;
  return days <= 0
    ? "Due today"
    : `${days} ${days === 1 ? "day" : "days"} overdue`;
}
export function daysAgo(value: string, now: number) {
  const days = Math.max(
    0,
    Math.floor((now - new Date(value).getTime()) / 86400000),
  );
  return days === 0 ? "Today" : days === 1 ? "1 day ago" : `${days} days ago`;
}
