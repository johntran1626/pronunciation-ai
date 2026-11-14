// Runs on the browser's audio thread (an "AudioWorklet"). Every 128 samples it receives the raw microphone
// samples and posts a mono copy to the page. No compression, so nothing has to be decoded later.
class PcmRecorder extends AudioWorkletProcessor {
  process(inputs) {
    const channels = inputs[0]; // first input; one Float32Array per channel
    if (channels && channels.length > 0) {
      const n = channels[0].length;
      const mono = new Float32Array(n);
      for (const ch of channels) for (let i = 0; i < n; i++) mono[i] += ch[i] / channels.length; // average to mono
      this.port.postMessage(mono, [mono.buffer]); // hand the buffer over without copying
    }
    return true; // keep running until the page disconnects us
  }
}
registerProcessor("pcm-recorder", PcmRecorder);
