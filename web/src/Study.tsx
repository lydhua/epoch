import { useEffect, useRef, useState } from "react";
import { Play, Pause, RotateCcw, ArrowUpRight } from "lucide-react";
import {
  ApiError,
  list,
  request,
  safeUrl,
  type Item,
  type Receipt,
  type Attempt,
} from "./api";
import {
  clockChanged,
  duration,
  elapsed,
  fresh,
  loadDraft,
  pause,
  type Draft,
} from "./timer";
import { Modal } from "./Modal";
import { minutes, outcomeName, timing } from "./practice";

const messageOf = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Could not acquire the practice lock.";

export function Study({
  item,
  owner,
  token,
  close,
  saved,
  startOnOpen = false,
}: {
  item: Item;
  owner: string;
  token: string;
  close: () => void;
  saved: (receipt: Receipt) => void;
  startOnOpen?: boolean;
}) {
  const key = `epoch:draft:v1:${owner}:${item.id}`;
  const [draft, setDraft] = useState<Draft>(fresh);
  const [locked, setLocked] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<Receipt[]>([]);
  const [now, setNow] = useState(Date.now);
  const submitting = useRef(false);
  const lockTask = useRef(Promise.resolve());
  const url = safeUrl(item.content.url);
  const startButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (startOnOpen && locked) startButton.current?.focus();
  }, [startOnOpen, locked]);
  useEffect(() => {
    let active = true;
    let release: (() => void) | undefined;
    if (!navigator.locks) {
      setError(
        "This browser cannot safely coordinate practice across tabs. Use a current browser on localhost or HTTPS.",
      );
      return;
    }
    lockTask.current = lockTask.current
      .then(async () => {
        if (!active) return;
        await navigator.locks.request(
          key,
          { ifAvailable: true },
          async (lock) => {
            if (!active) return;
            if (!lock) {
              setError(
                "This problem is open in another tab. Close it there and reopen it here.",
              );
              return;
            }
            try {
              setDraft(loadDraft(key));
              setLocked(true);
            } catch (e) {
              setError((e as Error).message);
            }
            await new Promise<void>((resolve) => {
              release = resolve;
            });
          },
        );
      })
      .catch((e) => {
        if (active) setError(messageOf(e));
      });
    return () => {
      active = false;
      release?.();
    };
  }, [key]);
  useEffect(() => {
    let active = true;
    list<Receipt>(token, `/items/${item.id}/attempts`)
      .then((result) => {
        if (active) setHistory(result.reverse());
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [token, item.id]);
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, []);
  function update(value: Draft) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
      setDraft(value);
      return true;
    } catch {
      setError(
        "Your browser could not save this draft. Free local storage before continuing.",
      );
      return false;
    }
  }
  useEffect(() => {
    if (locked && clockChanged(draft, now)) {
      update({ ...draft, started: null });
      setNotice(
        "The clock changed or the timer ran for over 12 hours. Timing was paused; enter a corrected duration before saving.",
      );
    }
  }, [now, locked]); // Draft is read on every clock tick.
  function start() {
    if (!update({ ...draft, measured: true, started: Date.now() })) return;
    if (url) {
      const tab = window.open("about:blank", "_blank");
      if (tab) {
        tab.opener = null;
        tab.location.href = url;
      } else
        setNotice(
          "The problem tab was blocked. Use “Open problem” below; your timer is running.",
        );
    }
  }
  async function submit() {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      let pending = draft.pending;
      if (!pending) {
        const stopped = pause(draft, Date.now());
        if (clockChanged(draft, Date.now()))
          throw new Error(
            "Check the timer and correct its duration before saving.",
          );
        const corrected =
          draft.correction.trim() === ""
            ? undefined
            : Number(draft.correction) * 60;
        if (
          corrected !== undefined &&
          (!Number.isFinite(corrected) || corrected < 0)
        )
          throw new Error("Enter a nonnegative duration in minutes.");
        pending = {
          id: crypto.randomUUID(),
          occurred_at: new Date().toISOString(),
          outcome: draft.outcome,
          timing: {
            ...(draft.measured
              ? { measured_seconds: stopped.elapsed / 1000 }
              : {}),
            ...(corrected === undefined
              ? {}
              : { corrected_seconds: corrected }),
          },
          confidence: draft.confidence ? Number(draft.confidence) : null,
        } satisfies Attempt;
        if (!update({ ...stopped, pending })) return;
      }
      const receipt = await request<Receipt>(
        token,
        `/items/${item.id}/attempts`,
        pending,
      );
      localStorage.removeItem(key);
      saved(receipt);
    } catch (e) {
      // A definitive validation rejection can be edited. Ambiguous transport errors
      // keep the exact ID and payload for replay, including across refreshes.
      if (e instanceof ApiError && e.status === 422) {
        const current = loadDraft(key);
        update({ ...current, pending: null });
      }
      setError((e as Error).message);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  const frozen = !locked || !!draft.pending || busy;
  return (
    <Modal
      title={item.title}
      close={() => {
        if (busy) return;
        if (
          locked &&
          draft.started !== null &&
          !update(pause(draft, Date.now()))
        )
          return;
        close();
      }}
    >
      {item.target_seconds != null && (
        <p className="study-goal">
          Time goal: <strong>{minutes(item.target_seconds)}</strong>
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      {url && (
        <a
          className="text-link"
          href={url}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open problem <ArrowUpRight size={16} />
        </a>
      )}
      {item.content.instructions && <p>{item.content.instructions}</p>}
      {item.content.front && (
        <>
          <p>{item.content.front}</p>
          <details>
            <summary>Reveal answer</summary>
            <p>{item.content.back}</p>
          </details>
        </>
      )}
      <section className="timer" aria-label="Optional practice timer">
        <span className="eyebrow">TIMER · OPTIONAL</span>
        <div className="timer-digits" aria-label="Elapsed time">
          {duration(elapsed(draft, now))}
        </div>
        <div className="actions centered">
          {!draft.measured ? (
            <button ref={startButton} disabled={frozen} onClick={start}>
              <Play size={16} /> Start & open
            </button>
          ) : draft.started === null ? (
            <button
              disabled={frozen}
              onClick={() => update({ ...draft, started: Date.now() })}
            >
              <Play size={16} /> Resume
            </button>
          ) : (
            <button
              disabled={frozen}
              onClick={() => update(pause(draft, Date.now()))}
            >
              <Pause size={16} /> Pause
            </button>
          )}
          <button
            className="quiet"
            disabled={frozen || !draft.measured}
            onClick={() => {
              if (
                confirm(
                  "Reset measured time? This clears the timer and any duration correction.",
                )
              )
                update({
                  ...draft,
                  elapsed: 0,
                  started: null,
                  measured: false,
                  correction: "",
                });
            }}
          >
            <RotateCcw size={16} /> Reset
          </button>
        </div>
        <p className="small muted timer-note">
          Closing pauses the timer. Refreshing preserves it.
        </p>
      </section>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <fieldset disabled={frozen}>
          <legend>How did it go?</legend>
          <div className="outcomes">
            {[
              ["independent", "Solved independently"],
              ["with_hints", "Used a hint"],
              ["consulted_solution", "Read the solution"],
              ["not_solved", "Not solved yet"],
            ].map(([value, label]) => (
              <label
                className={draft.outcome === value ? "selected" : ""}
                key={value}
              >
                <input
                  type="radio"
                  name="outcome"
                  value={value}
                  checked={draft.outcome === value}
                  onChange={() => update({ ...draft, outcome: value })}
                />
                {label}
              </label>
            ))}
          </div>
          <div className="form-grid">
            <label>
              Manual / corrected minutes
              <input
                type="number"
                min="0"
                step="any"
                placeholder="Optional"
                value={draft.correction}
                onChange={(e) =>
                  update({ ...draft, correction: e.target.value })
                }
              />
            </label>
            <label>
              Confidence
              <select
                value={draft.confidence}
                onChange={(e) =>
                  update({ ...draft, confidence: e.target.value })
                }
              >
                <option value="">Not recorded</option>
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n} / 5
                  </option>
                ))}
              </select>
            </label>
          </div>
        </fieldset>
        <p className="small muted">
          {draft.measured
            ? `Measured time: ${duration(elapsed(draft, now))}.`
            : "No measured time will be recorded."}{" "}
          Corrections are saved separately.
        </p>
        {draft.pending && (
          <p className="notice">
            This submission is saved locally. Retry sends the same attempt,
            without creating a duplicate.
          </p>
        )}
        <button
          className="primary wide"
          disabled={!locked || busy}
          type="submit"
        >
          {busy
            ? "Saving…"
            : draft.pending
              ? "Retry saved attempt"
              : "Save attempt"}
        </button>
      </form>
      <details className="history">
        <summary>Attempt history · {history.length}</summary>
        {history.length === 0 ? (
          <p className="muted">No attempts recorded.</p>
        ) : (
          history.map((r) => (
            <div className="history-row" key={r.attempt.id}>
              <div>
                <strong>{outcomeName(r.attempt.outcome)}</strong>
                <time>{new Date(r.attempt.occurred_at).toLocaleString()}</time>
              </div>
              <div className="history-timing">
                <strong>{timing(r)}</strong>
                {r.attempt.timing.corrected_seconds != null && (
                  <span className="muted">
                    {r.attempt.timing.measured_seconds != null
                      ? `Corrected · measured ${minutes(r.attempt.timing.measured_seconds)}`
                      : "Manually entered"}
                  </span>
                )}
              </div>
            </div>
          ))
        )}
      </details>
    </Modal>
  );
}
