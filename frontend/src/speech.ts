// MediaRecorder -> local STT, adapted from pilot2/agent d3aea330/frontend/speech.js.
// Transcription never invokes route search or stores audio.
export type SpeechState = "idle" | "permission" | "recording" | "transcribing";
export type SpeechEnvironment = {
  getUserMedia: () => Promise<MediaStream>;
  supports: (type: string) => boolean;
  recorder: (stream: MediaStream, type: string) => MediaRecorder;
  transcribe: (audio: Blob, signal: AbortSignal) => Promise<string>;
};

export async function transcribeAudio(audio: Blob, signal: AbortSignal): Promise<string> {
  const response = await fetch("/api/speech/transcribe", {
    method: "POST", headers: { "Content-Type": audio.type }, body: audio, signal,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof data?.detail === "string" ? data.detail : "음성 변환에 실패했습니다. 잠시 후 다시 시도해 주세요.");
  if (typeof data?.text !== "string" || !data.text.trim() || data.text.length > 500) {
    throw new Error("인식된 문장이 없습니다. 다시 녹음해 주세요.");
  }
  return data.text.trim();
}

export const browserSpeechEnvironment = (): SpeechEnvironment => ({
  getUserMedia: () => navigator.mediaDevices.getUserMedia({ audio: true }),
  supports: (type) => MediaRecorder.isTypeSupported(type),
  recorder: (stream, type) => new MediaRecorder(stream, { mimeType: type }),
  transcribe: transcribeAudio,
});

export class SpeechCapture {
  private generation = 0;
  private stream?: MediaStream;
  private recorder?: MediaRecorder;
  private timer?: ReturnType<typeof setTimeout>;
  private controller?: AbortController;
  private state: SpeechState = "idle";
  private env: SpeechEnvironment;
  private notify: (state: SpeechState) => void;
  private receive: (text: string, revision: number) => void;

  constructor(
    env: SpeechEnvironment,
    notify: (state: SpeechState) => void,
    receive: (text: string, revision: number) => void,
  ) { this.env = env; this.notify = notify; this.receive = receive; }

  private update(state: SpeechState) {
    this.state = state;
    this.notify(state);
  }

  private release() {
    clearTimeout(this.timer);
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = undefined;
  }

  cancel(notify = true) {
    this.generation++;
    if (this.recorder) {
      this.recorder.onstop = null;
      this.recorder.onerror = null;
      this.recorder.ondataavailable = null;
      if (this.recorder.state === "recording") this.recorder.stop();
      this.recorder = undefined;
    }
    this.release();
    this.controller?.abort();
    this.state = "idle";
    if (notify) this.notify("idle");
  }

  stop() {
    if (this.recorder?.state === "recording") this.recorder.stop();
  }

  async start(revision: number) {
    if (this.state !== "idle") return;
    const generation = ++this.generation;
    this.update("permission");
    try {
      const type = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"]
        .find((value) => this.env.supports(value));
      if (!type) throw new Error("Unsupported audio format");
      const stream = await this.env.getUserMedia();
      if (generation !== this.generation) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      this.stream = stream;
      const recorder = this.env.recorder(stream, type);
      this.recorder = recorder;
      const chunks: Blob[] = [];
      let size = 0;
      recorder.ondataavailable = (event) => {
        if (generation !== this.generation) return;
        size += event.data.size;
        if (size > 8 * 1024 * 1024) {
          this.cancel(false);
          this.update("idle");
        } else if (event.data.size) chunks.push(event.data);
      };
      recorder.onerror = () => {
        this.cancel(false);
        this.update("idle");
      };
      recorder.onstop = async () => {
        this.release();
        if (generation !== this.generation) return;
        this.update("transcribing");
        const controller = new AbortController();
        this.controller = controller;
        const timeout = setTimeout(() => controller.abort(), 180000);
        try {
          if (!size) throw new Error("Empty recording");
          const text = await this.env.transcribe(new Blob(chunks, { type }), controller.signal);
          if (generation !== this.generation) return;
          this.update("idle");
          this.receive(text, revision);
        } catch {
          if (generation === this.generation) this.update("idle");
        } finally { clearTimeout(timeout); }
      };
      recorder.start(1000);
      this.update("recording");
      this.timer = setTimeout(() => this.stop(), 29000);
    } catch {
      if (generation !== this.generation) return;
      this.release();
      this.update("idle");
    }
  }
}
