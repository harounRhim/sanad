/**
 * Encode a recorded audio Blob (typically webm/opus from MediaRecorder) into a
 * 16 kHz mono 16-bit PCM WAV Blob.
 *
 * The correction API's aligner expects 16 kHz mono; doing the decode + resample
 * in the browser means the server needs NO ffmpeg — soundfile/torchaudio read
 * plain WAV natively. We use the Web Audio API (decodeAudioData) to decode
 * whatever the browser recorded, then an OfflineAudioContext to resample to 16k.
 */

const TARGET_SR = 16000;

export async function blobToWav16kMono(blob: Blob): Promise<Blob> {
  const arrayBuf = await blob.arrayBuffer();

  // Decode using a throwaway AudioContext (its own sample rate is irrelevant).
  const AudioCtx: typeof AudioContext =
    window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const decodeCtx = new AudioCtx();
  let decoded: AudioBuffer;
  try {
    decoded = await decodeCtx.decodeAudioData(arrayBuf.slice(0));
  } finally {
    void decodeCtx.close();
  }

  return resampleTo16kMono(decoded);
}

/**
 * Same resample-to-16kHz-mono step as `blobToWav16kMono`, but starting from
 * raw Float32 PCM already in hand (useRollingRecorder's ring buffer) instead
 * of an encoded Blob — skips the decodeAudioData step, which only applies to
 * container formats (webm/opus) we don't have here.
 */
export async function pcmFloat32ToWav16kMono(
  samples: Float32Array<ArrayBuffer>, sourceSampleRate: number
): Promise<Blob> {
  const AudioCtx: typeof AudioContext =
    window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const ctx = new AudioCtx();
  let buf: AudioBuffer;
  try {
    buf = ctx.createBuffer(1, samples.length, sourceSampleRate);
    buf.copyToChannel(samples, 0);
  } finally {
    void ctx.close();
  }
  return resampleTo16kMono(buf);
}

async function resampleTo16kMono(decoded: AudioBuffer): Promise<Blob> {
  // Resample to 16 kHz mono via an offline render (1 output channel downmixes).
  const frames = Math.max(1, Math.ceil(decoded.duration * TARGET_SR));
  const offline = new OfflineAudioContext(1, frames, TARGET_SR);
  const src = offline.createBufferSource();
  src.buffer = decoded;
  src.connect(offline.destination);
  src.start();
  const rendered = await offline.startRendering();

  return encodePcm16Wav(rendered.getChannelData(0), TARGET_SR);
}

/** Little-endian 16-bit PCM WAV container around a Float32 mono channel. */
function encodePcm16Wav(samples: Float32Array, sampleRate: number): Blob {
  const bytesPerSample = 2;
  const dataSize = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeStr = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };

  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true); // PCM chunk size
  view.setUint16(20, 1, true); // audio format = PCM
  view.setUint16(22, 1, true); // channels = 1
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * bytesPerSample, true); // byte rate
  view.setUint16(32, bytesPerSample, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeStr(36, "data");
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += bytesPerSample;
  }

  return new Blob([buffer], { type: "audio/wav" });
}
