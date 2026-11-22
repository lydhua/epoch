export type Collection = { id: string; owner_id: string; name: string };
export type Decision = {
  state: string;
  attempts: number;
  independent_successes: number;
  next_due_at: string | null;
  reason: string;
};
export type Item = {
  id: string;
  collection_id: string;
  title: string;
  tags: string[];
  is_due: boolean;
  content: {
    type: string;
    url?: string;
    difficulty?: string;
    instructions?: string;
    front?: string;
    back?: string;
  };
  schedule: { decision: Decision };
  target_seconds: number | null;
};
export type Attempt = {
  id: string;
  occurred_at: string;
  outcome: string;
  timing: { measured_seconds?: number; corrected_seconds?: number };
  confidence: number | null;
};
export type Receipt = { attempt: Attempt; decision: Decision };

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function request<T>(
  token: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api" + path, {
    signal: AbortSignal.timeout(15000),
    method: body === undefined ? "GET" : "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const message =
      response.status === 401
        ? "Your session expired. Reconnect with a fresh local token."
        : typeof data.detail === "string"
          ? data.detail
          : Array.isArray(data.detail)
            ? data.detail
                .map(
                  (e: { loc: string[]; msg: string }) =>
                    `${e.loc.slice(1).join(".")}: ${e.msg}`,
                )
                .join("; ")
            : `Request failed (${response.status}). Please try again.`;
    throw new ApiError(response.status, message);
  }
  return response.json();
}
export async function list<T>(token: string, path: string): Promise<T[]> {
  const result: T[] = [];
  for (let offset = 0; offset <= 10000; offset += 100) {
    const page = await request<T[]>(
      token,
      `${path}?limit=100&offset=${offset}`,
    );
    result.push(...page);
    if (page.length < 100) return result;
  }
  throw new Error(
    "This collection is too large for this preview. Narrower server-side filtering is needed.",
  );
}
export function safeUrl(url?: string) {
  try {
    const parsed = new URL(url || "");
    return parsed.protocol === "https:" && !parsed.username && !parsed.password
      ? parsed.href
      : undefined;
  } catch {
    return undefined;
  }
}
