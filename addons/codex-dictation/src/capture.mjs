// Hold early speech until the remote service is ready, then replay it in order at normal speed.
// PCM stays in RAM and the outgoing track remains silent until release().
export function createCapture({ onLevel = () => {}, Context = globalThis.AudioContext, Worklet = globalThis.AudioWorkletNode } = {}) {
  const context = new Context();
  const pending = [], playing = new Set();
  let node, source, destination, stream, released = false, closed = false, muted = false;
  let nextTime = 0, bufferedSamples = 0, flushResolve;
  const flushed = new Promise(resolve => { flushResolve = resolve; });
  function play(samples) {
    const audio = context.createBuffer(1, samples.length, context.sampleRate);
    audio.copyToChannel(samples, 0);
    const player = context.createBufferSource(); player.buffer = audio; player.connect(destination);
    nextTime = Math.max(context.currentTime + 0.02, nextTime);
    player.start(nextTime); nextTime += samples.length / context.sampleRate;
    playing.add(player); player.onended = () => { playing.delete(player); player.disconnect(); };
  }
  return {
    async prepare() {
      await context.resume();
      await context.audioWorklet.addModule(new URL('./capture-worklet.mjs', import.meta.url));
      if (closed) return;
      destination = context.createMediaStreamDestination();
      node = new Worklet(context, 't3-dictation-capture', { channelCount: 1, numberOfInputs: 1, numberOfOutputs: 1 });
      node.connect(context.destination);
      node.port.onmessage = ({ data }) => {
        if (closed) return;
        if (data.flushed) { node.disconnect(); source?.disconnect(); flushResolve(); return; }
        const samples = data.samples;
        if (!(samples instanceof Float32Array)) return;
        let power = 0; for (const sample of samples) power += sample * sample;
        onLevel(Math.min(1, Math.sqrt(power / samples.length) * 7));
        if (released) play(samples);
        else {
          bufferedSamples += samples.length;
          if (bufferedSamples > context.sampleRate * 45) {
            // Fail visibly instead of silently dropping the beginning of a long connection attempt.
            this.error = new Error('The voice connection took too long. Stop and try again.');
            stream?.getTracks().forEach(t => t.stop());
            return;
          }
          pending.push(samples);
        }
      };
    },
    attach(microphone) {
      stream = microphone;
      source = context.createMediaStreamSource(stream); source.connect(node);
      return destination.stream;
    },
    release() {
      if (this.error) throw this.error;
      if (closed) return;
      released = true;
      for (const samples of pending.splice(0)) play(samples);
      bufferedSamples = 0;
    },
    mute() {
      if (muted || closed) return;
      muted = true; stream?.getTracks().forEach(t => t.stop());
      if (node) node.port.postMessage('flush'); else flushResolve();
      onLevel(0);
    },
    async drain() {
      await flushed;
      if (closed) return;
      const remaining = Math.max(0, nextTime - context.currentTime);
      if (remaining) await new Promise(resolve => setTimeout(resolve, remaining * 1000 + 100));
    },
    close() {
      if (closed) return;
      closed = true; pending.length = 0; flushResolve();
      stream?.getTracks().forEach(t => t.stop());
      source?.disconnect(); node?.disconnect(); node?.port.close();
      for (const player of playing) { player.onended = null; player.stop(); player.disconnect(); }
      playing.clear(); destination?.stream.getTracks().forEach(t => t.stop());
      void context.close();
    },
  };
}
