import { useState } from "react";
import { localDay, outcomeName, timing, type PracticeEvent } from "./practice";

export function Activity({
  events,
  now,
  loading,
  failed,
  open,
}: {
  events: PracticeEvent[];
  now: number;
  loading: boolean;
  failed: boolean;
  open: (event: PracticeEvent) => void;
}) {
  const year = new Date(now).getFullYear();
  const [selected, setSelected] = useState<string | null>(null);
  const days = new Map<string, PracticeEvent[]>();
  for (const event of events) {
    const day = localDay(new Date(event.receipt.attempt.occurred_at));
    days.set(day, [...(days.get(day) || []), event]);
  }
  const first = new Date(year, 0, 1, 12);
  const last = new Date(year, 11, 31, 12);
  const cells: (Date | null)[] = Array.from(
    { length: first.getDay() },
    () => null,
  );
  for (const day = new Date(first); day <= last; day.setDate(day.getDate() + 1))
    cells.push(new Date(day));
  while (cells.length % 7) cells.push(null);
  const weeks = Array.from({ length: cells.length / 7 }, (_, i) =>
    cells.slice(i * 7, i * 7 + 7),
  );
  const count = events.filter(
    (e) => new Date(e.receipt.attempt.occurred_at).getFullYear() === year,
  ).length;
  return (
    <section className="activity panel" aria-label="Practice activity">
      <header className="section-heading row-between">
        <h2>Practice activity</h2>
        <span className="muted">{year}</span>
      </header>
      {failed ? (
        <p role="status" className="activity-status">
          Activity could not be loaded. Refresh to try again.
        </p>
      ) : loading ? (
        <p role="status" className="activity-status">
          Loading activity…
        </p>
      ) : (
        <>
          <p className="activity-total">
            <strong>{count}</strong> {count === 1 ? "attempt" : "attempts"} this
            year <span>· First attempts and reviews</span>
          </p>
          <div className="calendar-scroll">
            <div
              className="calendar"
              style={{
                gridTemplateColumns: `repeat(${weeks.length}, minmax(10px, 1fr))`,
              }}
            >
              {weeks.map((week, i) => (
                <div className="calendar-week" key={i}>
                  <span className="month-label">
                    {week
                      .find((d) => d?.getDate() === 1)
                      ?.toLocaleDateString(undefined, { month: "short" }) || ""}
                  </span>
                  {week.map((day, j) => {
                    if (!day)
                      return <span className="day-placeholder" key={j} />;
                    const key = localDay(day);
                    const total = days.get(key)?.length || 0;
                    const label = `${day.toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" })}: ${total} ${total === 1 ? "attempt" : "attempts"}`;
                    return (
                      <button
                        key={key}
                        className={`calendar-day level-${Math.min(total, 4)} ${selected === key ? "chosen" : ""}`}
                        disabled={key > localDay(new Date(now))}
                        aria-label={label}
                        aria-pressed={selected === key}
                        title={label}
                        onClick={() =>
                          setSelected(selected === key ? null : key)
                        }
                      />
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
          <div className="calendar-caption">
            <span>
              Dates in {Intl.DateTimeFormat().resolvedOptions().timeZone}
            </span>
            <span className="legend">
              Less{" "}
              {[0, 1, 2, 3, 4].map((n) => (
                <i aria-hidden="true" key={n} className={`level-${n}`} />
              ))}{" "}
              More
            </span>
          </div>
          {selected && (
            <div className="activity-day">
              <h3>
                {new Date(selected + "T12:00:00").toLocaleDateString(
                  undefined,
                  { month: "long", day: "numeric" },
                )}
              </h3>
              {!days.get(selected)?.length ? (
                <p className="muted">No attempts recorded.</p>
              ) : (
                days.get(selected)!.map((event) => (
                  <button
                    key={event.receipt.attempt.id}
                    className="activity-entry"
                    onClick={() => open(event)}
                  >
                    <span>{event.item.title}</span>
                    <span className="muted">
                      {outcomeName(event.receipt.attempt.outcome)} ·{" "}
                      {timing(event.receipt)}
                    </span>
                  </button>
                ))
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
