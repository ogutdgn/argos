"use client";

import { useEffect, useRef, useState } from "react";
import { CircleAlert, Clock, Heart } from "lucide-react";
import { PersonAvatar } from "@/components/person-avatar";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { VoiceRecorder, type VoiceSample } from "@/components/voice-recorder";
import { uploadToTarget } from "@/lib/supabase/upload";
import { prepareInviteUploads, submitInvite } from "./actions";
import { LINK_USED, MessageCard } from "./message";

// The registration form behind the magic link (docs/flows.md, Flow A): name,
// relationship, things to talk about, photo, voice sample. Family members are
// often older and on a phone, so it is one column, large targets, plain words.
//
// Submitting: the server makes one-time upload targets, the browser uploads
// the photo and voice straight to storage, then the server saves everything
// and uses up the link (app/invite/[token]/actions.ts).

const PHOTO_ACCEPT = "image/jpeg,image/png,image/webp";
const MAX_PHOTO_BYTES = 10 * 1024 * 1024; // the photos bucket limit

const UPLOAD_ERROR = "That didn't send. Please check your connection and try again.";

type Done = "saved" | "used" | null;

export function InviteForm({ token, expiresOn }: { token: string; expiresOn: string }) {
  const [name, setName] = useState("");
  const [relationship, setRelationship] = useState("");
  const [facts, setFacts] = useState("");
  const [sharedMemories, setSharedMemories] = useState("");
  const [recentEvents, setRecentEvents] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [voice, setVoice] = useState<VoiceSample | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState<Done>(null);
  // Blocks a second submit before React re-renders the disabled button.
  const sending = useRef(false);

  useEffect(() => {
    if (!photoUrl) return;
    return () => URL.revokeObjectURL(photoUrl);
  }, [photoUrl]);

  function choosePhoto(file: File | undefined) {
    setPhotoError(null);
    setPhoto(null);
    setPhotoUrl(null);
    if (!file) return;
    if (!PHOTO_ACCEPT.split(",").includes(file.type)) {
      setPhotoError("Please choose a JPEG, PNG or WebP photo.");
      return;
    }
    if (file.size > MAX_PHOTO_BYTES) {
      setPhotoError("That photo is larger than 10 MB. Please choose a smaller one.");
      return;
    }
    setPhoto(file);
    setPhotoUrl(URL.createObjectURL(file));
  }

  const hasMemory = [facts, sharedMemories, recentEvents].some((v) => v.trim());
  const missing = [
    !name.trim() && "your name",
    !relationship.trim() && "how you are related",
    !hasMemory && "one thing to talk about",
    !photo && "a photo",
    !voice && "your voice",
  ].filter((v): v is string => Boolean(v));
  const ready = missing.length === 0;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ready || !photo || !voice || sending.current) return;
    sending.current = true;
    setSaving(true);
    setError(null);

    try {
      const prepared = await prepareInviteUploads({ token, photoType: photo.type });
      if (!prepared.ok) {
        if (prepared.reason === "used") setDone("used");
        else setError(prepared.error);
        return;
      }

      const uploads = await Promise.all([
        uploadToTarget(prepared.voice, voice.blob, "audio/wav"),
        uploadToTarget(prepared.photo, photo, photo.type),
      ]);
      if (uploads.some((u) => !u.ok)) {
        setError(UPLOAD_ERROR);
        return;
      }

      const saved = await submitInvite({
        token,
        name,
        relationship,
        facts,
        sharedMemories,
        recentEvents,
        voiceSamplePath: prepared.voice.path,
        photoPath: prepared.photo.path,
      });
      if (saved.ok) setDone("saved");
      else if (saved.reason === "used") setDone("used");
      else setError(saved.error);
    } catch {
      setError(UPLOAD_ERROR);
    } finally {
      sending.current = false;
      setSaving(false);
    }
  }

  // Bring the answer into view: the button was at the bottom of a long page.
  useEffect(() => {
    if (done) window.scrollTo({ top: 0 });
  }, [done]);

  if (done === "saved") {
    return (
      <MessageCard
        icon={<Heart size={20} strokeWidth={1.75} aria-hidden />}
        title={`Thank you, ${name.trim()}`}
        text="Everything is saved. When you next visit, Argos can quietly tell your family member who is there and suggest something to talk about. You can close this page now."
      />
    );
  }
  if (done === "used") {
    return (
      <MessageCard icon={<Clock size={20} strokeWidth={1.75} aria-hidden />} {...LINK_USED} />
    );
  }

  return (
    <form onSubmit={submit} className="mx-auto flex w-full max-w-xl flex-col gap-6">
      <header className="flex flex-col gap-3">
        <span className="font-serif text-2xl font-semibold">Argos</span>
        <h1 className="text-3xl font-semibold">Add yourself</h1>
        <p className="text-muted">
          Argos helps your family member feel at ease when you visit, by
          quietly reminding them who you are and one thing to talk about. This
          takes about five minutes. Your link keeps working until {expiresOn}.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>About you</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <Label htmlFor="name">Your name</Label>
            <Input
              id="name"
              name="name"
              autoComplete="name"
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={saving}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="relationship">How you are related</Label>
            <Input
              id="relationship"
              name="relationship"
              autoComplete="off"
              required
              maxLength={100}
              aria-describedby="relationship-hint"
              value={relationship}
              onChange={(e) => setRelationship(e.target.value)}
              disabled={saving}
            />
            <p id="relationship-hint" className="text-sm text-muted">
              For example: son, granddaughter or old friend.
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="photo">A photo of you</Label>
            <div className="flex items-center gap-4">
              {photoUrl && (
                <PersonAvatar name={name || "?"} photoUrl={photoUrl} className="size-16 shrink-0" />
              )}
              <Input
                id="photo"
                name="photo"
                type="file"
                accept={PHOTO_ACCEPT}
                required
                aria-invalid={photoError ? true : undefined}
                aria-describedby="photo-hint"
                onChange={(e) => choosePhoto(e.target.files?.[0])}
                disabled={saving}
                className="h-auto min-h-12 file:mr-3 file:min-h-9 file:cursor-pointer file:rounded-control file:border-0 file:bg-subtle file:px-3 file:text-sm file:font-medium file:text-ink"
              />
            </div>
            <p id="photo-hint" className="text-sm text-muted">
              {photoError ?? "A clear photo of your face, shown to the family in Argos."}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Things to talk about</h2>
          </CardTitle>
          <CardDescription>
            Fill in at least one. Put each thing on its own line.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <MemoryField
            id="facts"
            label="About your life"
            hint="Things that stay the same, like where you live or what you do."
            placeholder="I live in Ithaca with my wife."
            value={facts}
            onChange={setFacts}
            disabled={saving}
          />
          <MemoryField
            id="shared-memories"
            label="Memories you share"
            hint="Moments you remember together."
            placeholder="We planted the pear trees together."
            value={sharedMemories}
            onChange={setSharedMemories}
            disabled={saving}
          />
          <MemoryField
            id="recent-events"
            label="Recent news"
            hint="What is new for you these days."
            placeholder="I just came back from a trip to Sparta."
            value={recentEvents}
            onChange={setRecentEvents}
            disabled={saving}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Your voice</h2>
          </CardTitle>
          <CardDescription>
            Read the text below aloud at an easy pace, in a quiet room. It
            takes 20 to 30 seconds, and lets Argos know your voice when you
            visit.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <VoiceRecorder onChange={setVoice} disabled={saving} />
        </CardContent>
      </Card>

      {error && (
        <Alert variant="danger">
          <CircleAlert strokeWidth={1.75} aria-hidden />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-col gap-3 pb-8">
        <Button type="submit" disabled={!ready || saving} className="min-h-12 w-full text-base">
          {saving ? "Sending…" : "Send"}
        </Button>
        {!ready && !saving && (
          <p className="text-sm text-muted">Still needed: {list(missing)}.</p>
        )}
      </div>
    </form>
  );
}

function list(items: string[]) {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

function MemoryField({
  id,
  label,
  hint,
  placeholder,
  value,
  onChange,
  disabled,
}: {
  id: string;
  label: string;
  hint: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      <p id={`${id}-hint`} className="text-sm text-muted">
        {hint}
      </p>
      <Textarea
        id={id}
        name={id}
        rows={3}
        maxLength={4000}
        aria-describedby={`${id}-hint`}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      />
    </div>
  );
}
