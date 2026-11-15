import { createClient } from "./server";
import { signedUrls } from "./storage";

// The people table (docs/structure.md, "The contract"). Dashboard reads use
// the signed-in user's client, so RLS applies.

export type Person = {
  id: string;
  name: string;
  relationship: string | null;
  isPatient: boolean;
  photoPath: string | null;
  voiceSamplePath: string | null;
  createdAt: string;
};

export type PersonWithMedia = Person & {
  photoUrl: string | null;
  voiceSampleUrl: string | null;
};

type PersonRow = {
  id: string;
  name: string;
  relationship: string | null;
  is_patient: boolean;
  photo_path: string | null;
  voice_sample_path: string | null;
  created_at: string;
};

const COLUMNS =
  "id, name, relationship, is_patient, photo_path, voice_sample_path, created_at";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID.test(value);
}

function toPerson(row: PersonRow): Person {
  return {
    id: row.id,
    name: row.name,
    relationship: row.relationship,
    isPatient: row.is_patient,
    photoPath: row.photo_path,
    voiceSamplePath: row.voice_sample_path,
    createdAt: row.created_at,
  };
}

// Everyone, the patient first, then by name. Photos come as signed URLs.
export async function listPeople(): Promise<(Person & { photoUrl: string | null })[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("people")
    .select(COLUMNS)
    .order("is_patient", { ascending: false })
    .order("name");
  if (error) throw error;

  const people = (data as PersonRow[]).map(toPerson);
  const photos = await signedUrls(
    "photos",
    people.map((p) => p.photoPath),
    supabase,
  );
  return people.map((p) => ({
    ...p,
    photoUrl: p.photoPath ? (photos.get(p.photoPath) ?? null) : null,
  }));
}

// One person with signed photo and voice sample URLs, or null.
export async function getPerson(id: string): Promise<PersonWithMedia | null> {
  if (!isUuid(id)) return null;
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("people")
    .select(COLUMNS)
    .eq("id", id)
    .maybeSingle();
  if (error) throw error;
  if (!data) return null;

  const person = toPerson(data as PersonRow);
  const [photos, voices] = await Promise.all([
    signedUrls("photos", [person.photoPath], supabase),
    signedUrls("voice-samples", [person.voiceSamplePath], supabase),
  ]);
  return {
    ...person,
    photoUrl: person.photoPath ? (photos.get(person.photoPath) ?? null) : null,
    voiceSampleUrl: person.voiceSamplePath
      ? (voices.get(person.voiceSamplePath) ?? null)
      : null,
  };
}

export async function getPatient(): Promise<Person | null> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("people")
    .select(COLUMNS)
    .eq("is_patient", true)
    .maybeSingle();
  if (error) throw error;
  return data ? toPerson(data as PersonRow) : null;
}

export type CreatePatientResult =
  | { ok: true }
  | { ok: false; reason: "patient_exists" | "error" };

// Inserts the patient row with the id the uploads were made under.
export async function createPatient(input: {
  id: string;
  name: string;
  photoPath: string | null;
  voiceSamplePath: string;
}): Promise<CreatePatientResult> {
  const supabase = await createClient();
  const { error } = await supabase.from("people").insert({
    id: input.id,
    name: input.name,
    relationship: null,
    is_patient: true,
    photo_path: input.photoPath,
    voice_sample_path: input.voiceSamplePath,
  });
  if (!error) return { ok: true };
  // people_one_patient: at most one row with is_patient = true.
  if (error.code === "23505") return { ok: false, reason: "patient_exists" };
  return { ok: false, reason: "error" };
}
