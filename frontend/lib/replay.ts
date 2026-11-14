// Play back just one word / syllable of the learner's own recording.
// sliceBounds is pure (tested in replay.test.ts); playSlice uses Web Audio (browser only).

export const PAD_SECONDS = 0.06; // extra audio each side: forced-alignment edges are ~tens of ms off (spikes/d_align.py)

// start/end (seconds, from the aligner) -> which stretch to play, padded and kept inside the recording.
export function sliceBounds(
  start: number | null | undefined,
  end: number | null | undefined,
  total: number,
  pad = PAD_SECONDS,
): { offset: number; duration: number } | null {
  if (start == null || end == null || end < start) return null;
  const offset = Math.max(0, start - pad);
  const stop = Math.min(total, end + pad);
  return { offset, duration: stop - offset };
}

let ctx: AudioContext | null = null;
let current: AudioBufferSourceNode | null = null;
const buffers = new WeakMap<Float32Array, AudioBuffer>(); // one AudioBuffer per recording, made on first tap

export function stopPlayback() {
  if (current) {
    current.onended = null;
    current.stop();
    current = null;
  }
}

// Play samples[start..end] (padded). Stops whatever was playing. Returns false if there's nothing to play.
export function playSlice(
  samples: Float32Array<ArrayBuffer>,
  rate: number,
  start: number | null | undefined,
  end: number | null | undefined,
  onEnd?: () => void,
  pad = PAD_SECONDS, // The animation plays single sounds with a smaller pad
): boolean {
  const b = sliceBounds(start, end, samples.length / rate, pad);
  if (!b) return false;
  ctx ??= new AudioContext(); // the browser resamples our 16 kHz buffer to the speakers' rate
  void ctx.resume();
  stopPlayback();
  let buffer = buffers.get(samples);
  if (!buffer) {
    buffer = ctx.createBuffer(1, samples.length, rate);
    buffer.copyToChannel(samples, 0);
    buffers.set(samples, buffer);
  }
  const src = ctx.createBufferSource();
  src.buffer = buffer;
  src.connect(ctx.destination);
  src.onended = () => {
    if (current === src) current = null;
    onEnd?.();
  };
  src.start(0, b.offset, b.duration);
  current = src;
  return true;
}
