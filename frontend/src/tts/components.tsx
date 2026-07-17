// TTS UI: a per-message speak button and a header auto-speak toggle.

import { useEffect, useState } from "react";
import { VolumeUp, VolumeMute, Pause } from "@carbon/icons-react";
import { cancelSpeech, getVoices, speak, ttsSupported, useTts } from "./tts";

/** Speak a single message aloud (toggles play/stop). */
export function SpeakButton({ text }: { text: string }) {
  const speaking = useTts((s) => s.speaking);
  const [mine, setMine] = useState(false);
  if (!ttsSupported || !text.trim()) return null;

  const active = speaking && mine;
  return (
    <button
      className={"epmw-speak" + (active ? " active" : "")}
      title={active ? "Stop reading" : "Read aloud"}
      aria-label={active ? "Stop reading" : "Read aloud"}
      onClick={() => {
        if (active) {
          cancelSpeech();
          setMine(false);
        } else {
          speak(text);
          setMine(true);
        }
      }}
    >
      {active ? <Pause size={14} /> : <VolumeUp size={14} />}
    </button>
  );
}

/** Header control: toggle auto-speak of new assistant replies + pick a voice. */
export function TtsToggle() {
  const { autoSpeak, setAutoSpeak, speaking, voiceUri, setVoice, rate, setRate } = useTts();
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [openMenu, setOpenMenu] = useState(false);

  useEffect(() => {
    if (!ttsSupported) return;
    const load = () => setVoices(getVoices());
    load();
    window.speechSynthesis.onvoiceschanged = load;
    return () => { window.speechSynthesis.onvoiceschanged = null; };
  }, []);

  if (!ttsSupported) return null;

  return (
    <div className="epmw-tts-ctl">
      <button
        className={"epmw-tts-toggle" + (autoSpeak ? " active" : "")}
        title={autoSpeak ? "Auto-read replies: on" : "Auto-read replies: off"}
        aria-pressed={autoSpeak}
        onClick={() => { if (autoSpeak && speaking) cancelSpeech(); setAutoSpeak(!autoSpeak); }}
      >
        {autoSpeak ? <VolumeUp size={16} /> : <VolumeMute size={16} />}
      </button>
      <button className="epmw-tts-more" title="Voice settings" onClick={() => setOpenMenu((o) => !o)}>▾</button>
      {openMenu && (
        <div className="epmw-tts-menu" onMouseLeave={() => setOpenMenu(false)}>
          <label>Voice
            <select value={voiceUri ?? ""} onChange={(e) => setVoice(e.target.value || null)}>
              <option value="">Default</option>
              {voices.map((v) => <option key={v.voiceURI} value={v.voiceURI}>{v.name}</option>)}
            </select>
          </label>
          <label>Speed {rate.toFixed(1)}×
            <input type="range" min={0.6} max={1.6} step={0.1} value={rate} onChange={(e) => setRate(Number(e.target.value))} />
          </label>
        </div>
      )}
    </div>
  );
}
