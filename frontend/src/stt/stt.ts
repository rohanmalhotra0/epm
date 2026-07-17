// Speech-to-text (browser Web Speech API — no backend, no keys).
//
// Mirrors the TTS module: a small persisted zustand store for the recognition
// language, plus a React hook that manages a SpeechRecognition session and
// streams interim + final transcripts back to the caller (the composer).
//
// Note: the Web Speech *recognition* API is not in the standard TS DOM lib, so
// minimal typings are declared here.

import { useCallback, useEffect, useRef, useState } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";

// --- minimal Web Speech API typings ----------------------------------------

interface SpeechRecognitionAlt {
  transcript: string;
}
interface SpeechRecognitionResultLike {
  isFinal: boolean;
  0: SpeechRecognitionAlt;
  length: number;
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
}
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error?: string }) => void) | null;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  }
}

function recognitionCtor(): SpeechRecognitionCtor | undefined {
  if (typeof window === "undefined") return undefined;
  return window.SpeechRecognition || window.webkitSpeechRecognition;
}

/** True if the browser supports speech recognition (evaluated live). */
export function isSttSupported(): boolean {
  return !!recognitionCtor();
}

// --- settings store ---------------------------------------------------------

interface SttState {
  lang: string;
  setLang: (l: string) => void;
}

export const useSttSettings = create<SttState>()(
  persist(
    (set) => ({ lang: "en-US", setLang: (lang) => set({ lang }) }),
    { name: "epmw-stt" },
  ),
);

export const STT_LANGS = [
  { code: "en-US", label: "English (US)" },
  { code: "en-GB", label: "English (UK)" },
  { code: "es-ES", label: "Spanish" },
  { code: "fr-FR", label: "French" },
  { code: "de-DE", label: "German" },
  { code: "pt-BR", label: "Portuguese (BR)" },
  { code: "ja-JP", label: "Japanese" },
];

// --- hook -------------------------------------------------------------------

export interface UseStt {
  supported: boolean;
  listening: boolean;
  error: string | null;
  start: () => void;
  stop: () => void;
  toggle: () => void;
}

/**
 * Manage a dictation session. `onTranscript(text, isFinal)` receives interim
 * updates (isFinal=false, replace-in-place) and committed segments (isFinal=true).
 */
export function useSpeechRecognition(onTranscript: (text: string, isFinal: boolean) => void): UseStt {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const cbRef = useRef(onTranscript);
  cbRef.current = onTranscript;
  const lang = useSttSettings((s) => s.lang);
  const supported = isSttSupported();

  const stop = useCallback(() => {
    recRef.current?.stop();
  }, []);

  const start = useCallback(() => {
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    if (recRef.current) {
      recRef.current.abort();
      recRef.current = null;
    }
    const rec = new Ctor();
    rec.lang = lang;
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    rec.onstart = () => {
      setError(null);
      setListening(true);
    };
    rec.onerror = (e) => {
      setError(e?.error || "recognition error");
      setListening(false);
    };
    rec.onend = () => {
      setListening(false);
      recRef.current = null;
    };
    rec.onresult = (e) => {
      let interim = "";
      let final = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        const text = r[0]?.transcript ?? "";
        if (r.isFinal) final += text;
        else interim += text;
      }
      if (final) cbRef.current(final.trim(), true);
      else if (interim) cbRef.current(interim.trim(), false);
    };
    recRef.current = rec;
    try {
      rec.start();
    } catch {
      /* already started */
    }
  }, [lang]);

  const toggle = useCallback(() => {
    if (recRef.current) stop();
    else start();
  }, [start, stop]);

  useEffect(() => {
    return () => {
      recRef.current?.abort();
      recRef.current = null;
    };
  }, []);

  return { supported, listening, error, start, stop, toggle };
}
