import { useState } from "react";
import { ArrowRight, Plus } from "lucide-react";
import { request, safeUrl, type Collection, type Item } from "./api";
import { Modal } from "./Modal";

export const message = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
export function canonical(url: string) {
  const safe = safeUrl(url);
  if (!safe) return "";
  const parsed = new URL(safe);
  const problem =
    parsed.hostname.replace(/^www\./, "") === "leetcode.com" &&
    parsed.pathname.match(/^\/problems\/([^/]+)/);
  return problem
    ? `https://leetcode.com/problems/${problem[1]}/`
    : `${parsed.origin}${parsed.pathname.replace(/\/$/, "")}${parsed.search}`;
}
export function Connect({
  connect,
  error: initialError,
}: {
  connect: (value: string) => void;
  error: string;
}) {
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function login(demo: boolean) {
    setBusy(true);
    setError("");
    try {
      let token = value.trim();
      if (demo) {
        const response = await fetch("/api/demo-session");
        if (!response.ok)
          throw new Error(
            "No local demo is running. Connect with a local API token.",
          );
        token = (await response.json()).token;
      }
      await request(token, "/collections?limit=1");
      connect(token);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="connect-page">
      <div className="connect-card">
        <div className="brand">
          <span className="brand-mark">e</span>epoch
          <span className="brand-dot">.</span>
        </div>
        <h1>
          Interview practice,
          <br />
          spaced out.
        </h1>
        <p className="muted">
          Review problems, track solve times, and plan your next attempt.
        </p>
        <button
          className="primary wide"
          disabled={busy}
          onClick={() => void login(true)}
        >
          Explore local demo <ArrowRight size={17} />
        </button>
        <details>
          <summary>Connect to your local API</summary>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void login(false);
            }}
          >
            <label>
              Local bearer token
              <input
                type="password"
                autoComplete="off"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                required
              />
            </label>
            <button className="wide" disabled={busy || !value.trim()}>
              Connect
            </button>
          </form>
        </details>
        {(error || initialError) && (
          <p className="error" role="alert">
            {error || initialError}
          </p>
        )}
        <p className="small muted">
          Local development preview. Tokens stay in this tab’s session storage.
        </p>
      </div>
    </main>
  );
}
export function Create({
  kind,
  token,
  collections,
  items,
  selected,
  close,
  done,
}: {
  kind: "item" | "collection";
  token: string;
  collections: Collection[];
  items: Item[];
  selected: string;
  close: () => void;
  done: () => void;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  function changeUrl(value: string) {
    setUrl(value);
    if (!title) {
      const match = canonical(value).match(/leetcode.com\/problems\/([^/]+)/);
      if (match)
        setTitle(
          match[1]
            .split("-")
            .map((word) => word[0]?.toUpperCase() + word.slice(1))
            .join(" "),
        );
    }
  }
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      if (
        kind === "item" &&
        items.some(
          (item) =>
            canonical(item.content.url || "") === canonical(url) &&
            canonical(url),
        )
      )
        throw new Error("This problem is already in your library.");
      await request(
        token,
        kind === "item" ? "/items" : "/collections",
        kind === "collection"
          ? { name: data.get("name") }
          : {
              collection_id: data.get("collection"),
              title: title.trim(),
              content: {
                type: "coding_problem",
                url: canonical(url) || url,
                difficulty: data.get("difficulty") || null,
              },
              tags: String(data.get("tags"))
                .split(",")
                .map((t) => t.trim())
                .filter(Boolean),
              target_seconds: data.get("goal")
                ? Number(data.get("goal")) * 60
                : null,
            },
      );
      done();
    } catch (e) {
      setError(
        message(e) +
          " If the connection failed, check your library before adding it again.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={kind === "item" ? "Add problem" : "New collection"}
      close={() => {
        if (!busy) close();
      }}
    >
      <form onSubmit={submit}>
        <fieldset disabled={busy}>
          {kind === "collection" ? (
            <label>
              Collection name
              <input
                name="name"
                required
                maxLength={200}
                placeholder="e.g. Interview prep"
              />
            </label>
          ) : (
            <>
              <label>
                Problem link
                <input
                  type="url"
                  name="url"
                  pattern="https://.*"
                  value={url}
                  onChange={(e) => changeUrl(e.target.value)}
                  required
                  maxLength={2048}
                  placeholder="https://leetcode.com/problems/…"
                />
              </label>
              <label>
                Problem title
                <input
                  name="title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  required
                  maxLength={300}
                  placeholder="e.g. 1. Two Sum"
                />
              </label>
              <div className="form-grid">
                <label>
                  Difficulty
                  <select name="difficulty">
                    <option value="">Not specified</option>
                    {["easy", "medium", "hard"].map((d) => (
                      <option key={d} value={d}>
                        {d[0].toUpperCase() + d.slice(1)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Time goal in minutes <span className="muted">· optional</span>
                  <input
                    type="number"
                    name="goal"
                    min="0.01"
                    step="any"
                    placeholder="e.g. 20"
                  />
                </label>
              </div>
              <label>
                Collection
                <select
                  name="collection"
                  defaultValue={
                    collections.some((c) => c.id === selected)
                      ? selected
                      : collections[0]?.id
                  }
                >
                  {collections.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Topics{" "}
                <span className="muted">· optional, comma separated</span>
                <input name="tags" placeholder="Arrays, two pointers" />
              </label>
            </>
          )}
        </fieldset>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <button className="primary wide" disabled={busy}>
          {busy
            ? "Saving…"
            : kind === "item"
              ? "Add problem"
              : "Create collection"}
          <Plus size={17} />
        </button>
      </form>
    </Modal>
  );
}
