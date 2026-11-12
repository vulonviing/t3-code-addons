// Batch microphone PCM in memory. The output is silent; audio is sent only by the replay graph.
class DictationCapture extends AudioWorkletProcessor {
  constructor() {
    super(); this.buffer = new Float32Array(2048); this.used = 0;
    this.port.onmessage = ({ data }) => { if (data === 'flush') { this.flush(); this.port.postMessage({ flushed: true }); } };
  }
  flush() {
    if (!this.used) return;
    const samples = this.buffer.slice(0, this.used);
    this.port.postMessage({ samples }, [samples.buffer]); this.used = 0;
  }
  process(inputs) {
    const samples = inputs[0]?.[0];
    if (samples) for (let i = 0; i < samples.length; i++) {
      this.buffer[this.used++] = samples[i];
      if (this.used === this.buffer.length) this.flush();
    }
    return true;
  }
}
registerProcessor('t3-dictation-capture', DictationCapture);
