"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CircleAlert } from "lucide-react";
import { PersonAvatar } from "@/components/person-avatar";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { VoiceRecorder, type VoiceSample } from "@/components/voice-recorder";
import { uploadToTarget } from "@/lib/supabase/upload";
import { addPatient, preparePatientUploads } from "../actions";

const PHOTO_ACCEPT = "image/jpeg,image/png,image/webp";
const MAX_PHOTO_BYTES = 10 * 1024 * 1024; // the photos bucket limit

const UPLOAD_ERROR = "The recording didn't upload. Please try again in a moment.";

export function AddPatientForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [voice, setVoice] = useState<VoiceSample | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Free the preview URL when the photo changes or the page goes away.
  useEffect(() => {
    if (!photoUrl) return;
    return () => URL.revokeObjectURL(photoUrl);
  }, [photoUrl]);

  function choosePhoto(file: File | undefined) {
    setPhotoError(null);
    if (!file) {
      setPhoto(null);
      setPhotoUrl(null);
      return;
    }
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

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!voice || !name.trim()) return;
    setSaving(true);
    setError(null);

    try {
      const prepared = await preparePatientUploads({ photoType: photo?.type ?? null });
      if (!prepared.ok) {
        setError(prepared.error);
        return;
      }

      const uploads = await Promise.all([
        uploadToTarget(prepared.voice, voice.blob, "audio/wav"),
        photo && prepared.photo
          ? uploadToTarget(prepared.photo, photo, photo.type)
          : Promise.resolve({ ok: true as const }),
      ]);
      if (uploads.some((u) => !u.ok)) {
        setError(UPLOAD_ERROR);
        return;
      }

      const added = await addPatient({
        personId: prepared.personId,
        name,
        voiceSamplePath: prepared.voice.path,
        photoPath: prepared.photo?.path ?? null,
      });
      if (!added.ok) {
        setError(added.error);
        return;
      }
      router.push(`/people/${prepared.personId}`);
    } catch {
      setError(UPLOAD_ERROR);
    } finally {
      setSaving(false);
    }
  }

  const ready = Boolean(voice) && name.trim().length > 0;

  return (
    <form onSubmit={submit} className="flex max-w-2xl flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Profile</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              name="name"
              autoComplete="off"
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="photo">Photo (optional)</Label>
            <div className="flex items-center gap-4">
              {photoUrl && (
                <PersonAvatar name={name || "?"} photoUrl={photoUrl} className="size-16" />
              )}
              <Input
                id="photo"
                name="photo"
                type="file"
                accept={PHOTO_ACCEPT}
                aria-invalid={photoError ? true : undefined}
                aria-describedby="photo-hint"
                onChange={(e) => choosePhoto(e.target.files?.[0])}
                className="file:mr-3 file:cursor-pointer file:rounded-control file:border-0 file:bg-subtle file:px-3 file:py-1 file:text-sm file:font-medium file:text-ink"
              />
            </div>
            <p id="photo-hint" className="text-sm text-muted">
              {photoError ?? "Shown in the dashboard. JPEG, PNG or WebP, up to 10 MB."}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Voice sample</h2>
          </CardTitle>
          <CardDescription>
            About 20 to 30 seconds of the patient reading the text below, so
            Argos knows their voice and never mistakes it for a visitor.
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

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <Button type="submit" disabled={!ready || saving}>
          {saving ? "Saving…" : "Add the patient"}
        </Button>
        {!ready && !saving && (
          <p className="text-sm text-muted">
            Add a name and a voice sample to continue.
          </p>
        )}
      </div>
    </form>
  );
}
