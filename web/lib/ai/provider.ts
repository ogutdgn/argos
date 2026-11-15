import "server-only";

// The only file that talks to the AI provider (docs/tech.md: OpenAI
// gpt-5-mini until the demo, Google after). Swapping providers means
// rewriting generateText() and isAiConfigured() here, nothing else.

const MODEL = "gpt-5-mini";
const ENDPOINT = "https://api.openai.com/v1/chat/completions";
const TIMEOUT_MS = 30_000;

export function isAiConfigured() {
  return Boolean(process.env.OPENAI_API_KEY);
}

// One instruction + one input → the model's text answer. Throws on any
// failure (missing key, HTTP error, timeout, empty answer).
export async function generateText({
  instructions,
  input,
}: {
  instructions: string;
  input: string;
}): Promise<string> {
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
      reasoning_effort: "low", // one short sentence needs little reasoning; keeps it fast
      messages: [
        { role: "developer", content: instructions },
        { role: "user", content: input },
      ],
    }),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(`OpenAI answered ${res.status}`);

  const data = (await res.json()) as {
    choices?: { message?: { content?: string | null } }[];
  };
  const text = data.choices?.[0]?.message?.content?.trim();
  if (!text) throw new Error("OpenAI gave an empty answer");
  return text;
}
