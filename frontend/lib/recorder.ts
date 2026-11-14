// Browser recording: microphone -> raw samples (AudioWorklet) -> 16 kHz mono -> WAV.
// Browser-only (uses the microphone and Web Audio), so it's checked by hand / headless Chrome; the WAV math is
// tested in wav.test.ts.
//
// Fix after the first real-device test ("Unable to decode audio data"): we used to record with MediaRecorder
// (compressed webm/mp4) and decode it afterwards; that decode failed on his mic setup. Now we capture the raw
// samples directly, so there is no compression and no decode step. Bonus: no lossy codec smearing f/s/th.
import { encodeWav16, louderForPlayback, trimToSeconds } from "./wav.ts";

export const MAX_SECONDS = 15; // hard limit; the backend rejects longer recordings
export const TARGET_RATE = 16000; // what the wav2vec2 model was trained on

export type RecordedAudio = { samples: Float32Array<ArrayBuffer>; sampleRate: number };
export type Recording = { stop: () => Promise<RecordedAudio> };

// Ask for the microphone and start recording. Resolves once recording has actually begun.
export async function startRecording(): Promise<Recording> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      // Phone-call clean-up filters are OFF: they're tuned for voices on calls and can smear
      // exactly what we measure (the hiss of f/s/th, quiet bursts of p/t/k).
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
    },
  });
  const ctx = new AudioContext(); // runs at the device's rate (often 48 kHz); we resample at the end
  try {
    await ctx.audioWorklet.addModule("/pcm-recorder-worklet.js");
  } catch (e) {
    stream.getTracks().forEach((t) => t.stop());
    ctx.close();
    throw e;
  }
  const source = ctx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(ctx, "pcm-recorder");
  const chunks: Float32Array[] = [];
  node.port.onmessage = (e: MessageEvent<Float32Array>) => chunks.push(e.data);
  source.connect(node);
  node.connect(ctx.destination); // the worklet writes no output (silence); connecting keeps the graph running
  await ctx.resume(); // some browsers start an AudioContext "suspended"

  return {
    stop: async () => {
      source.disconnect();
      node.disconnect();
      stream.getTracks().forEach((t) => t.stop()); // release the mic (the browser's red dot goes away)
      const sampleRate = ctx.sampleRate;
      await ctx.close();
      const samples = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
      let at = 0;
      for (const c of chunks) {
        samples.set(c, at);
        at += c.length;
      }
      return { samples, sampleRate };
    },
  };
}

// Numbers for the debug panel: is the audio we send actually speech-loud, and how long?
export type AudioStats = { micRate: number; seconds: number; peak: number; rmsDb: number };

function stats(samples: Float32Array, micRate: number, rate: number): AudioStats {
  let peak = 0;
  let sumSq = 0;
  for (const s of samples) {
    peak = Math.max(peak, Math.abs(s));
    sumSq += s * s;
  }
  const rms = Math.sqrt(sumSq / Math.max(1, samples.length));
  // dBFS: 0 = the loudest a file can hold; normal speech on a laptop mic is roughly -35 to -15.
  return { micRate, seconds: samples.length / rate, peak, rmsDb: 20 * Math.log10(rms || 1e-9) };
}

// Raw samples at the mic's rate -> 16 kHz mono 16-bit WAV (at most MAX_SECONDS) + a louder copy to play back + stats.
export async function toWav16k(
  { samples, sampleRate }: RecordedAudio,
): Promise<{ wav: Blob; playback: Blob; playbackSamples: Float32Array<ArrayBuffer>; stats: AudioStats }> {
  if (samples.length < sampleRate * 0.1) {
    throw new Error("The recording came out empty. Check the microphone (System Settings → Sound → Input) and try again.");
  }
  // An "offline" context renders as fast as possible instead of playing. At 16 kHz it resamples for us.
  const offline = new OfflineAudioContext(1, Math.ceil((samples.length / sampleRate) * TARGET_RATE), TARGET_RATE);
  const buffer = offline.createBuffer(1, samples.length, sampleRate);
  buffer.copyToChannel(samples, 0);
  const source = offline.createBufferSource();
  source.buffer = buffer;
  source.connect(offline.destination);
  source.start();
  const rendered = await offline.startRendering();

  const out = trimToSeconds(rendered.getChannelData(0), TARGET_RATE, MAX_SECONDS);
  const louder = louderForPlayback(out); // for listening only (the whole-recording player + per-part replay)
  return {
    playbackSamples: louder,
    wav: new Blob([encodeWav16(out, TARGET_RATE)], { type: "audio/wav" }), // sent to /analyze, original level
    playback: new Blob([encodeWav16(louder, TARGET_RATE)], { type: "audio/wav" }),
    stats: stats(out, sampleRate, TARGET_RATE),
  };
}
