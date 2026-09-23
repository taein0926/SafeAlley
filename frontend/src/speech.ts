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
  private notify: (state: SpeechState, message: string) => void;
  private receive: (text: string, revision: number) => void;

  constructor(
    env: SpeechEnvironment,
    notify: (state: SpeechState, message: string) => void,
    receive: (text: string, revision: number) => void,
  ) { this.env = env; this.notify = notify; this.receive = receive; }

  private update(state: SpeechState, message: string) {
    this.state = state;
    this.notify(state, message);
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
    if (notify) this.notify("idle", "음성 입력을 취소했습니다.");
  }

  stop() {
    if (this.recorder?.state === "recording") this.recorder.stop();
  }

  async start(revision: number) {
    if (this.state !== "idle") return;
    const generation = ++this.generation;
    this.update("permission", "마이크 권한을 확인하는 중…");
    try {
      const type = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"]
        .find((value) => this.env.supports(value));
      if (!type) throw new Error("지원하는 녹음 형식이 없습니다. Chrome/Edge에서 직접 입력해 주세요.");
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
          this.update("idle", "녹음 크기가 8MB를 초과했습니다. 짧게 다시 녹음해 주세요.");
        } else if (event.data.size) chunks.push(event.data);
      };
      recorder.onerror = () => {
        this.cancel(false);
        this.update("idle", "녹음 오류가 발생했습니다. 마이크를 확인해 주세요.");
      };
      recorder.onstop = async () => {
        this.release();
        if (generation !== this.generation) return;
        this.update("transcribing", "로컬에서 음성을 변환하는 중… 최초 사용은 모델 준비로 더 걸릴 수 있습니다.");
        const controller = new AbortController();
        this.controller = controller;
        const timeout = setTimeout(() => controller.abort(), 180000);
        try {
          if (!size) throw new Error("녹음 내용이 없습니다. 다시 녹음해 주세요.");
          const text = await this.env.transcribe(new Blob(chunks, { type }), controller.signal);
          if (generation !== this.generation) return;
          this.update("idle", "인식된 출발지·도착지·조건을 확인한 뒤 경로 검색을 눌러 주세요.");
          this.receive(text, revision);
        } catch (error) {
          if (generation === this.generation) this.update("idle", error instanceof Error && error.name === "AbortError"
            ? "음성 변환 시간이 초과됐습니다. 잠시 후 다시 시도해 주세요."
            : error instanceof Error ? error.message : "음성 변환에 실패했습니다.");
        } finally { clearTimeout(timeout); }
      };
      recorder.start(1000);
      this.update("recording", "녹음 중… 같은 버튼을 다시 누르면 중지하고 텍스트로 변환합니다. 최대 30초까지 녹음합니다.");
      this.timer = setTimeout(() => this.stop(), 29000);
    } catch (error) {
      if (generation !== this.generation) return;
      this.release();
      this.update("idle", error instanceof Error && error.name === "NotAllowedError"
        ? "마이크 권한이 거부됐습니다. 브라우저 권한을 확인하거나 직접 입력해 주세요."
        : "마이크를 사용할 수 없습니다. 장치 연결과 브라우저 지원을 확인해 주세요.");
    }
  }
}
