import "server-only";

// The only file that talks to the AI provider (docs/tech.md: OpenAI
// gpt-5-mini until the demo, Google after). Swapping providers means
// rewriting this file, nothing else.

const MODEL = "gpt-5-mini";
const ENDPOINT = "https://api.openai.com/v1/chat/completions";

export function isAiConfigured() {
  return Boolean(process.env.OPENAI_API_KEY);
}

type Request = {
  instructions: string;
  input: string;
  effort: "low" | "medium"; // how much the model reasons before answering
  timeoutMs: number;
  // Set: the answer must be JSON that fits this JSON Schema.
  schema?: { name: string; schema: Record<string, unknown> };
};

// Throws on any failure (missing key, HTTP error, timeout, empty answer).
async function complete({ instructions, input, effort, timeoutMs, schema }: Request) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error("OPENAI_API_KEY is not set");

  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: MODEL,
      reasoning_effort: effort,
      messages: [
        { role: "developer", content: instructions },
        { role: "user", content: input },
      ],
      ...(schema && {
        response_format: {
          type: "json_schema",
          json_schema: { name: schema.name, strict: true, schema: schema.schema },
        },
      }),
    }),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) throw new Error(`OpenAI answered ${res.status}`);

  const data = (await res.json()) as {
    choices?: { message?: { content?: string | null } }[];
  };
  const text = data.choices?.[0]?.message?.content?.trim();
  if (!text) throw new Error("OpenAI gave an empty answer");
  return text;
}

// One instruction + one input → a short text answer.
export function generateText(request: { instructions: string; input: string }) {
  // One short sentence needs little reasoning; low keeps it fast.
  return complete({ ...request, effort: "low", timeoutMs: 30_000 });
}

// One instruction + one input → JSON that fits `schema`. The result is
// parsed but not checked: callers must check every field themselves.
export async function generateJson(request: {
  instructions: string;
  input: string;
  schema: { name: string; schema: Record<string, unknown> };
}): Promise<unknown> {
  // A whole transcript to read: more reasoning and more time.
  const text = await complete({ ...request, effort: "medium", timeoutMs: 120_000 });
  try {
    return JSON.parse(text);
  } catch {
    throw new Error("OpenAI gave an answer that isn't JSON");
  }
}
