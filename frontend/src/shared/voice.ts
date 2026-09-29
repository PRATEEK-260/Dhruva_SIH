// Voice out and voice in for the boat phone.
//
// Out, in order of preference:
//   1. online   Bhashini speaks the exact sentence (POST /api/voice/tts); the clip
//               is kept in Cache Storage so the same sentence replays at sea.
//   2. saved    that Bhashini clip, if this sentence was heard before.
//   3. shipped  the Bhashini clip for the verdict, generated onshore and shipped
//               in the app (public/voice/<lang>/<state>.wav).
//   4. phone    the phone's own speech engine, if it has a voice for the language.
// Whatever plays, the caller is told which, and the screen says so.
//
// In: record, convert to 16 kHz mono WAV in the browser, POST /api/voice/asr.

import type { Language } from "./capsule/codebook";
import type { VerdictState } from "./verdict";

export type VoiceSource = "bhashini" | "saved" | "shipped" | "phone" | "none";

const CACHE = "dhruva-voice-v1";
let current: HTMLAudioElement | null = null;
// Each speakAdvisory call takes a number. A newer call pauses the older one's
// audio, and the older call must then stop quietly, not read the pause as a
// failed source and fall through to the next one: two overlapping calls used
// to pause each other down the whole list and both report "none" while a clip
// was playing.
let generation = 0;

function stop(): void {
  current?.pause();
  current = null;
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}

function cacheKey(text: string, lang: Language): string {
  let h = 5381;
  for (let i = 0; i < text.length; i++) h = ((h << 5) + h + text.charCodeAt(i)) | 0;
  return `/voice-cache/${lang}/${(h >>> 0).toString(36)}.wav`;
}

async function play(blob: Blob): Promise<void> {
  stop();
  const audio = new Audio(URL.createObjectURL(blob));
  current = audio;
  await audio.play();
}

async function openCache(): Promise<Cache | null> {
  try {
    return "caches" in window ? await caches.open(CACHE) : null;
  } catch {
    return null;
  }
}

async function bhashini(text: string, lang: Language): Promise<Blob> {
  const res = await fetch("/api/voice/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, language: lang }),
  });
  if (!res.ok) throw new Error(`voice ${res.status}`);
  const blob = await res.blob();
  const cache = await openCache();
  await cache?.put(cacheKey(text, lang), new Response(blob.slice(), { headers: { "Content-Type": "audio/wav" } }));
  return blob;
}

function phoneVoice(text: string, lang: Language): boolean {
  if (!("speechSynthesis" in window)) return false;
  const voices = window.speechSynthesis.getVoices();
  const voice = voices.find((v) => v.lang.toLowerCase().startsWith(lang));
  if (!voice && lang !== "en") return false;
  stop();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = voice?.lang ?? "en-IN";
  if (voice) u.voice = voice;
  window.speechSynthesis.speak(u);
  return true;
}

export async function speakAdvisory(opts: {
  text: string;
  lang: Language;
  state: VerdictState;
  online: boolean;
}): Promise<VoiceSource | null> {
  const { text, lang, state, online } = opts;
  const mine = ++generation;
  const superseded = () => mine !== generation;
  // Fetch first, then play only if this call is still the newest.
  const attempt = async (get: () => Promise<Blob | null>): Promise<boolean | null> => {
    try {
      const blob = await get();
      if (superseded()) return null;
      if (!blob) return false;
      await play(blob);
      return true;
    } catch {
      return superseded() ? null : false;
    }
  };

  if (online && lang !== "en") {
    const ok = await attempt(() => bhashini(text, lang));
    if (ok === null) return null;
    if (ok) return "bhashini";
  }
  const cache = await openCache();
  const saved = await cache?.match(cacheKey(text, lang));
  if (saved) {
    const ok = await attempt(() => saved.blob());
    if (ok === null) return null;
    if (ok) return "saved";
  }
  if (lang !== "en") {
    const ok = await attempt(async () => {
      const res = await fetch(`/voice/${lang}/${state}.wav`);
      return res.ok ? res.blob() : null;
    });
    if (ok === null) return null;
    if (ok) return "shipped";
  }
  if (superseded()) return null;
  return phoneVoice(text, lang) ? "phone" : "none";
}

export function stopSpeaking(): void {
  stop();
}

// ------------------------------------------------------------------- in ----

export interface Recorder {
  stop: () => Promise<Blob>;
}

export async function startRecording(): Promise<Recorder> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const rec = new MediaRecorder(stream);
  const chunks: Blob[] = [];
  rec.ondataavailable = (e) => chunks.push(e.data);
  rec.start();
  return {
    stop: () =>
      new Promise((resolve) => {
        rec.onstop = () => {
          stream.getTracks().forEach((t) => t.stop());
          resolve(new Blob(chunks, { type: rec.mimeType }));
        };
        rec.stop();
      }),
  };
}

const ASR_RATE = 16000;

/** Any recorded format the browser can decode, to 16 kHz mono 16-bit WAV. */
export async function toWav16k(recording: Blob): Promise<Uint8Array> {
  const ctx = new AudioContext();
  const decoded = await ctx.decodeAudioData(await recording.arrayBuffer());
  await ctx.close();
  const frames = Math.ceil(decoded.duration * ASR_RATE);
  const offline = new OfflineAudioContext(1, frames, ASR_RATE);
  const src = offline.createBufferSource();
  src.buffer = decoded;
  src.connect(offline.destination);
  src.start();
  const pcm = (await offline.startRendering()).getChannelData(0);

  const out = new DataView(new ArrayBuffer(44 + pcm.length * 2));
  const w = (o: number, s: string) => [...s].forEach((c, i) => out.setUint8(o + i, c.charCodeAt(0)));
  w(0, "RIFF");
  out.setUint32(4, 36 + pcm.length * 2, true);
  w(8, "WAVE");
  w(12, "fmt ");
  out.setUint32(16, 16, true);
  out.setUint16(20, 1, true);
  out.setUint16(22, 1, true);
  out.setUint32(24, ASR_RATE, true);
  out.setUint32(28, ASR_RATE * 2, true);
  out.setUint16(32, 2, true);
  out.setUint16(34, 16, true);
  w(36, "data");
  out.setUint32(40, pcm.length * 2, true);
  pcm.forEach((s, i) => out.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 0x7fff, true));
  return new Uint8Array(out.buffer);
}

export async function transcribe(recording: Blob, lang: Language): Promise<string> {
  const wav = await toWav16k(recording);
  let binary = "";
  for (let i = 0; i < wav.length; i += 0x8000) {
    binary += String.fromCharCode(...wav.subarray(i, i + 0x8000));
  }
  const res = await fetch("/api/voice/asr", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ audio_base64: btoa(binary), language: lang, sample_rate: ASR_RATE }),
  });
  if (!res.ok) throw new Error(`Speech recognition failed (HTTP ${res.status})`);
  return ((await res.json()) as { text: string }).text;
}
