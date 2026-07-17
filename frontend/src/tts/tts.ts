// Text-to-speech (browser Web Speech API — no backend, no keys, offline).
//
// A small zustand store for the auto-speak toggle + rate + chosen voice, plus
// speak()/cancel() helpers that strip Markdown so assistant replies and report
// summaries read cleanly aloud.

import { create } from "zustand";
import { persist } from "zustand/middleware";

const synth: SpeechSynthesis | undefined =
  typeof window !== "undefined" ? window.speechSynthesis : undefined;

export const ttsSupported = Boolean(synth);

interface TtsState {
  autoSpeak: boolean;
  rate: number;
  voiceUri: string | null;
  speaking: boolean;
  setAutoSpeak: (v: boolean) => void;
  setRate: (r: number) => void;
  setVoice: (uri: string | null) => void;
  _setSpeaking: (v: boolean) => void;
}

export const useTts = create<TtsState>()(
  persist(
    (set) => ({
      autoSpeak: false,
      rate: 1,
      voiceUri: null,
      speaking: false,
      setAutoSpeak: (autoSpeak) => set({ autoSpeak }),
      setRate: (rate) => set({ rate }),
      setVoice: (voiceUri) => set({ voiceUri }),
      _setSpeaking: (speaking) => set({ speaking }),
    }),
    { name: "epmw-tts", partialize: (s) => ({ autoSpeak: s.autoSpeak, rate: s.rate, voiceUri: s.voiceUri }) },
  ),
);

/** Strip Markdown / code / tables to something that reads well aloud. */
export function toSpeech(md: string): string {
  return md
    .replace(/```[\s\S]*?```/g, " (code block) ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/[*_~]{1,3}/g, "")
    .replace(/^\s*\|.*\|\s*$/gm, "") // table rows
    .replace(/^\s*[-*+]\s+/gm, ", ")
    .replace(/\n{2,}/g, ". ")
    .replace(/\s+/g, " ")
    .trim();
}

export function getVoices(): SpeechSynthesisVoice[] {
  return synth ? synth.getVoices() : [];
}

/** Speak text aloud (cancels anything already playing). */
export function speak(text: string): void {
  if (!synth) return;
  const clean = toSpeech(text);
  if (!clean) return;
  synth.cancel();
  const u = new SpeechSynthesisUtterance(clean);
  const { rate, voiceUri, _setSpeaking } = useTts.getState();
  u.rate = rate;
  if (voiceUri) {
    const v = synth.getVoices().find((voice) => voice.voiceURI === voiceUri);
    if (v) u.voice = v;
  }
  u.onstart = () => _setSpeaking(true);
  u.onend = () => _setSpeaking(false);
  u.onerror = () => _setSpeaking(false);
  synth.speak(u);
}

export function cancelSpeech(): void {
  if (!synth) return;
  synth.cancel();
  useTts.getState()._setSpeaking(false);
}

/** True while something is being spoken. */
export function isSpeaking(): boolean {
  return synth ? synth.speaking : false;
}
