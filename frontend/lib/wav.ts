// Turn raw audio numbers into a WAV file. Pure functions: no browser APIs, so Node can test them.
//
// A WAV file = a 44-byte header that says how to read the numbers, then the numbers themselves
// (here 16-bit integers, little-endian, one channel).

// Keep at most `maxSeconds` of audio (the backend rejects anything over 15 s).
export function trimToSeconds(samples: Float32Array, sampleRate: number, maxSeconds: number): Float32Array {
  const max = Math.floor(sampleRate * maxSeconds);
  return samples.length > max ? samples.subarray(0, max) : samples;
}

// Float samples in [-1, 1] -> a mono 16-bit PCM WAV file.
export function encodeWav16(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const dataBytes = samples.length * 2;
  const buf = new ArrayBuffer(44 + dataBytes);
  const v = new DataView(buf);
  const text = (at: number, s: string) => [...s].forEach((c, i) => v.setUint8(at + i, c.charCodeAt(0)));

  text(0, "RIFF");
  v.setUint32(4, 36 + dataBytes, true); // bytes left in the file after this field
  text(8, "WAVE");
  text(12, "fmt ");
  v.setUint32(16, 16, true); // size of the format block
  v.setUint16(20, 1, true); // 1 = plain PCM
  v.setUint16(22, 1, true); // 1 channel
  v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate * 2, true); // bytes per second
  v.setUint16(32, 2, true); // bytes per sample frame
  v.setUint16(34, 16, true); // bits per sample
  text(36, "data");
  v.setUint32(40, dataBytes, true);

  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i])); // clip: 1.2 would otherwise wrap around to a loud click
    v.setInt16(44 + 2 * i, Math.round(s < 0 ? s * 32768 : s * 32767), true); // int16 runs -32768..32767
  }
  return buf;
}

// A LOUDER COPY for the playback button only. The analysis keeps the original level: the model rescales
// volume itself, and our acoustic checks use ratios, not loudness. Gain is capped so a near-silent
// recording doesn't turn into loud hiss, and loud audio is never turned down.
export function louderForPlayback(samples: Float32Array, targetPeak = 0.9, maxGain = 20): Float32Array<ArrayBuffer> {
  let peak = 0;
  for (const s of samples) peak = Math.max(peak, Math.abs(s));
  const gain = peak > 0 ? Math.min(maxGain, Math.max(1, targetPeak / peak)) : 1;
  return Float32Array.from(samples, (s) => s * gain);
}

// Read a 16-bit mono PCM WAV (the native Azure clip) back into float samples, so the "Native" button plays
// through the same slice player as YOUR audio. Walks the chunks instead of assuming a 44-byte header, because
// WAV files may carry extra blocks (LIST metadata...) before the audio. Refuses any other format.
export function decodeWav16(buf: ArrayBuffer): { samples: Float32Array<ArrayBuffer>; rate: number } {
  const v = new DataView(buf);
  const text = (at: number) => String.fromCharCode(v.getUint8(at), v.getUint8(at + 1), v.getUint8(at + 2), v.getUint8(at + 3));
  if (buf.byteLength < 12 || text(0) !== "RIFF" || text(8) !== "WAVE") throw new Error("Not a WAV file");
  let rate = 0;
  for (let at = 12; at + 8 <= buf.byteLength; ) {
    const id = text(at);
    const size = v.getUint32(at + 4, true);
    const body = at + 8;
    if (id === "fmt ") {
      const pcm = v.getUint16(body, true) === 1;
      const mono = v.getUint16(body + 2, true) === 1;
      const bits16 = v.getUint16(body + 14, true) === 16;
      if (!pcm || !mono || !bits16) throw new Error("Only 16-bit mono PCM WAV is supported");
      rate = v.getUint32(body + 4, true);
    } else if (id === "data") {
      if (!rate) throw new Error("WAV has no format block before its audio");
      const n = Math.floor(Math.min(size, buf.byteLength - body) / 2);
      const samples = new Float32Array(n);
      for (let i = 0; i < n; i++) {
        const x = v.getInt16(body + 2 * i, true);
        samples[i] = x < 0 ? x / 32768 : x / 32767; // the exact mirror of encodeWav16's scaling
      }
      return { samples, rate };
    }
    at = body + size + (size % 2); // chunks are padded to an even length
  }
  throw new Error("WAV has no audio data");
}
