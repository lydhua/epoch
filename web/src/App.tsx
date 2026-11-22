import { useEffect, useState } from "react";
import {
  ArrowUpRight,
  BookOpen,
  Check,
  Folder,
  Layers,
  LogOut,
  Plus,
  Search,
  Moon,
  Sun,
} from "lucide-react";
import { list, safeUrl, type Collection, type Item, type Receipt } from "./api";
import { Connect, Create, message } from "./Forms";
import { Study } from "./Study";
import { Activity } from "./Activity";
import {
  date,
  daysAgo,
  dueLabel,
  minutes,
  outcomeName,
  timing,
  type PracticeEvent,
} from "./practice";

type Theme = "light" | "dark" | "system";
export default function App() {
  const [token, setToken] = useState(() => {
    try {
      return sessionStorage.getItem("epoch:token") || "";
    } catch {
      return "";
    }
  });
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const t = localStorage.getItem("epoch:theme");
      return t === "light" || t === "dark" ? t : "system";
    } catch {
      return "system";
    }
  });
  const [collections, setCollections] = useState<Collection[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [events, setEvents] = useState<PracticeEvent[]>([]);
  const [activityLoading, setActivityLoading] = useState(false);
  const [activityFailed, setActivityFailed] = useState(false);
  const [view, setView] = useState("due");
  const [search, setSearch] = useState("");
  const [difficulty, setDifficulty] = useState("all");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [loading, setLoading] = useState(false);
  const [modal, setModal] = useState<"item" | "collection" | null>(null);
  const [study, setStudy] = useState<{ item: Item; start: boolean } | null>(
    null,
  );
  const [generation, setGeneration] = useState(0);
  const [clock, setClock] = useState(Date.now);
  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme =
        theme === "system" ? (media.matches ? "dark" : "light") : theme;
    };
    apply();
    media.addEventListener("change", apply);
    try {
      localStorage.setItem("epoch:theme", theme);
    } catch {
      /* Theme remains usable without persistence. */
    }
    return () => media.removeEventListener("change", apply);
  }, [theme]);
  useEffect(() => {
    const id = setInterval(() => setClock(Date.now()), 30000);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    if (!token) return;
    let active = true;
    setLoading(true);
    setError("");
    setActivityLoading(true);
    setActivityFailed(false);
    setEvents([]);
    void (async () => {
      try {
        const [c, i] = await Promise.all([
          list<Collection>(token, "/collections"),
          list<Item>(token, "/items"),
        ]);
        if (!active) return;
        setCollections(c);
        setItems(i);
        setLoading(false);
        // The existing API exposes item-scoped receipts. Limit parallel reads;
        // never use partial activity as a complete calendar or last-attempt record.
        let index = 0;
        const receipts: PracticeEvent[] = [];
        await Promise.all(
          Array.from({ length: Math.min(4, i.length) }, async () => {
            while (active && index < i.length) {
              const item = i[index++];
              const history = await list<Receipt>(
                token,
                `/items/${item.id}/attempts`,
              );
              for (const receipt of history) receipts.push({ item, receipt });
            }
          }),
        );
        if (active)
          setEvents(
            receipts.sort((a, b) =>
              b.receipt.attempt.occurred_at.localeCompare(
                a.receipt.attempt.occurred_at,
              ),
            ),
          );
      } catch (e) {
        if (active) {
          setError(message(e));
          setActivityFailed(true);
        }
      } finally {
        if (active) {
          setLoading(false);
          setActivityLoading(false);
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [token, generation]);
  function connect(value: string) {
    try {
      sessionStorage.setItem("epoch:token", value);
      setToken(value);
      setError("");
    } catch {
      setError("Enable session storage to use this preview.");
    }
  }
  function disconnect() {
    sessionStorage.removeItem("epoch:token");
    setToken("");
    setItems([]);
    setEvents([]);
    setCollections([]);
    setStudy(null);
    setView("due");
    setError("");
    setToast("");
  }
  const themeControl = (
    <label className="theme-control">
      <Moon size={15} />
      <span className="sr-only">Appearance</span>
      <select
        aria-label="Appearance"
        value={theme}
        onChange={(e) => setTheme(e.target.value as Theme)}
      >
        <option value="system">System</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
      <Sun size={15} />
    </label>
  );
  if (!token)
    return (
      <>
        <div className="connect-theme">{themeControl}</div>
        <Connect connect={connect} error={error} />
      </>
    );
  const ordered = [...items].sort(
    (a, b) =>
      (a.schedule.decision.next_due_at || "9999").localeCompare(
        b.schedule.decision.next_due_at || "9999",
      ) || a.id.localeCompare(b.id),
  );
  const due = ordered.filter(
    (i) =>
      i.schedule.decision.next_due_at &&
      new Date(i.schedule.decision.next_due_at).getTime() <= clock,
  );
  const recommended = due[0];
  const pool =
    view === "due"
      ? due.slice(1)
      : view === "queue"
        ? due
        : view === "all"
          ? ordered
          : ordered.filter((i) => i.collection_id === view);
  const filtered = pool.filter(
    (i) =>
      (difficulty === "all" || i.content.difficulty === difficulty) &&
      `${i.title} ${i.tags.join(" ")}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const latest = (item: Item) =>
    events.find((e) => e.item.id === item.id)?.receipt;
  const open = (item: Item, start = false) => setStudy({ item, start });
  function recorded(receipt: Receipt) {
    setStudy(null);
    setToast(
      `Attempt saved. Next practice: ${date(receipt.decision.next_due_at)}.`,
    );
    setGeneration((n) => n + 1);
  }
  const title =
    view === "due"
      ? "Today"
      : view === "all"
        ? "All problems"
        : view === "queue"
          ? "Review queue"
          : collections.find((c) => c.id === view)?.name || "Collection";
  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">
        Skip to practice
      </a>
      <aside className="sidebar">
        <a href="#main" className="brand" onClick={() => setView("due")}>
          <span className="brand-mark">e</span>epoch
          <span className="brand-dot">.</span>
        </a>
        <nav aria-label="Main navigation">
          <button
            className={`nav-item ${view === "due" ? "active" : ""}`}
            onClick={() => setView("due")}
          >
            <Layers size={18} />
            Today
          </button>
          <button
            className={`nav-item ${view === "queue" ? "active" : ""}`}
            onClick={() => setView("queue")}
          >
            <BookOpen size={18} />
            Review queue <span className="count">{due.length}</span>
          </button>
          <button
            className={`nav-item ${view === "all" ? "active" : ""}`}
            onClick={() => setView("all")}
          >
            <Folder size={18} />
            All problems
          </button>
        </nav>
        <div className="nav-label row-between">
          Collections
          <button
            className="icon"
            aria-label="New collection"
            onClick={() => setModal("collection")}
          >
            <Plus size={16} />
          </button>
        </div>
        <nav aria-label="Collections" className="collection-nav">
          {collections.map((c) => (
            <button
              key={c.id}
              className={`nav-item ${view === c.id ? "active" : ""}`}
              onClick={() => setView(c.id)}
            >
              <Folder size={16} />
              <span className="truncate">{c.name}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          {themeControl}
          <button className="nav-item" onClick={disconnect}>
            <LogOut size={17} />
            Disconnect
          </button>
          <span className="local-label">Local preview</span>
        </div>
      </aside>
      <div className="main-wrap">
        <header className="topbar">
          <span>Interview practice</span>
          <span>
            {new Date(clock).toLocaleDateString(undefined, {
              weekday: "short",
              month: "long",
              day: "numeric",
            })}
          </span>
        </header>
        <main id="main" tabIndex={-1}>
          <section className="heading">
            <h1>{title}</h1>
            <button
              className="primary"
              onClick={() =>
                setModal(collections.length ? "item" : "collection")
              }
            >
              <Plus size={18} />
              Add a problem
            </button>
          </section>
          {error && (
            <div role="alert" className="error row-between">
              <span>{error}</span>
              <button onClick={() => setGeneration((n) => n + 1)}>Retry</button>
            </div>
          )}
          {toast && (
            <div role="status" className="notice row-between">
              <span>
                <Check size={16} />
                {toast}
              </span>
              <button className="quiet" onClick={() => setToast("")}>
                Dismiss
              </button>
            </div>
          )}
          {view === "due" && (
            <section className="recommendation panel" aria-label="Next review">
              <div className="row-between">
                <span className="eyebrow">NEXT REVIEW</span>
                {recommended && (
                  <span className="badge">{dueLabel(recommended, clock)}</span>
                )}
              </div>
              {loading ? (
                <p role="status">Loading your next review…</p>
              ) : recommended ? (
                <>
                  <h2>
                    <ProblemLink item={recommended} />
                  </h2>
                  <span className="difficulty">
                    {recommended.content.difficulty || "Difficulty not set"}
                  </span>
                  <div className="review-facts">
                    <div>
                      <span className="fact-label">Last attempt</span>
                      <strong>
                        {activityLoading
                          ? "Loading…"
                          : activityFailed
                            ? "Unavailable"
                            : latest(recommended)
                              ? `${timing(latest(recommended))} · ${outcomeName(latest(recommended)!.attempt.outcome)}`
                              : "No attempts yet"}
                      </strong>
                      {latest(recommended) && (
                        <span className="muted">
                          {daysAgo(
                            latest(recommended)!.attempt.occurred_at,
                            clock,
                          )}
                        </span>
                      )}
                    </div>
                    <div>
                      <span className="fact-label">Time goal</span>
                      <strong>
                        {recommended.target_seconds == null
                          ? "Not set"
                          : minutes(recommended.target_seconds)}
                      </strong>
                    </div>
                  </div>
                  <div className="actions">
                    <button
                      className="primary"
                      aria-label={`Practice ${recommended.title}`}
                      onClick={() => open(recommended, true)}
                    >
                      Start review <ArrowUpRight size={17} />
                    </button>
                    <button onClick={() => open(recommended)}>
                      Record attempt
                    </button>
                  </div>
                </>
              ) : (
                <div className="empty">
                  <h2>
                    {items.length
                      ? "Nothing due right now"
                      : "No problems added"}
                  </h2>
                  <p className="muted">
                    {items.length
                      ? "Review another problem from your library or add a new one."
                      : "Add a problem to start your review queue."}
                  </p>
                  {items.length > 0 && (
                    <button onClick={() => setView("all")}>
                      Browse problems
                    </button>
                  )}
                </div>
              )}
            </section>
          )}
          <section className="queue-panel panel">
            <header className="section-heading row-between">
              <h2>{view === "due" ? "Other reviews" : title}</h2>
              {view === "due" && (
                <button
                  className="text-button"
                  onClick={() => setView("queue")}
                >
                  View queue ({due.length}) →
                </button>
              )}
            </header>
            <div className="filters">
              <label className="search">
                <Search size={17} />
                <span className="sr-only">Search problems</span>
                <input
                  placeholder="Search problems"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </label>
              <label className="difficulty-filter">
                <span className="sr-only">Difficulty filter</span>
                <select
                  aria-label="Difficulty filter"
                  value={difficulty}
                  onChange={(e) => setDifficulty(e.target.value)}
                >
                  <option value="all">All difficulties</option>
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
              </label>
            </div>
            {loading ? (
              <p className="empty" role="status">
                Loading problems…
              </p>
            ) : !filtered.length ? (
              <p className="empty muted">
                {search || difficulty !== "all"
                  ? "No matching problems."
                  : view === "due"
                    ? "No other reviews due."
                    : "No problems here yet."}
              </p>
            ) : (
              <ul className="problem-list">
                {(view === "due" ? filtered.slice(0, 3) : filtered).map(
                  (item) => (
                    <li key={item.id}>
                      <div className="problem-info">
                        <h3>
                          <ProblemLink item={item} />
                        </h3>
                        <div className="problem-meta">
                          <span className="difficulty">
                            {item.content.difficulty || "Unspecified"}
                          </span>
                          <span>·</span>
                          <span>{dueLabel(item, clock)}</span>
                        </div>
                        <p className="problem-time">
                          Last:{" "}
                          {activityLoading
                            ? "Loading…"
                            : activityFailed
                              ? "Unavailable"
                              : latest(item)
                                ? `${timing(latest(item))} · ${outcomeName(latest(item)!.attempt.outcome)}`
                                : "No attempts"}
                          {item.target_seconds != null &&
                            ` · Goal: ${minutes(item.target_seconds)}`}
                        </p>
                      </div>
                      <button
                        className="practice-button"
                        aria-label={`Practice ${item.title}`}
                        onClick={() => open(item)}
                      >
                        Review <ArrowUpRight size={16} />
                      </button>
                    </li>
                  ),
                )}
              </ul>
            )}
          </section>
          {view === "due" && (
            <Activity
              events={events}
              now={clock}
              loading={activityLoading}
              failed={activityFailed}
              open={(event) => open(event.item)}
            />
          )}
        </main>
      </div>
      {modal && (
        <Create
          kind={modal}
          token={token}
          collections={collections}
          items={items}
          selected={view}
          close={() => setModal(null)}
          done={() => {
            setModal(null);
            setGeneration((n) => n + 1);
            setToast(
              modal === "collection" ? "Collection created." : "Problem added.",
            );
          }}
        />
      )}
      {study && (
        <Study
          item={study.item}
          owner={
            collections.find((c) => c.id === study.item.collection_id)!.owner_id
          }
          token={token}
          startOnOpen={study.start}
          close={() => setStudy(null)}
          saved={recorded}
        />
      )}
    </div>
  );
}
function ProblemLink({ item }: { item: Item }) {
  const url = safeUrl(item.content.url);
  return url ? (
    <a
      className="problem-title"
      href={url}
      target="_blank"
      rel="noopener noreferrer"
    >
      {item.title}
      <ArrowUpRight size={16} />
    </a>
  ) : (
    <span className="problem-title">{item.title}</span>
  );
}
