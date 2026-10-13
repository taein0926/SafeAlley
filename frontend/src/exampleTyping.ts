type Options = {
  onText: (text: string, complete: boolean) => void;
  onTypingChange: (typing: boolean) => void;
  characterDelayMs?: number;
};

// This only animates input. The existing preview API interprets the text.
export function createExampleTyper(options: Options) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let disposed = false;
  let generation = 0;

  function cancel() {
    generation++;
    clearTimeout(timer);
    timer = undefined;
    options.onTypingChange(false);
  }

  return {
    start(text: string) {
      if (disposed) return;
      cancel();
      const session = generation;
      const characters = Array.from(text);
      let index = 0;
      let typed = "";
      options.onText("", false);
      options.onTypingChange(true);
      function tick() {
        if (disposed || generation !== session) return;
        typed += characters[index++];
        const complete = index === characters.length;
        options.onText(typed, complete);
        if (complete) { timer = undefined; options.onTypingChange(false); return; }
        timer = setTimeout(tick, options.characterDelayMs ?? 55);
      }
      if (characters.length) timer = setTimeout(tick, options.characterDelayMs ?? 55);
      else { options.onText("", true); options.onTypingChange(false); }
    },
    cancel,
    dispose() { cancel(); disposed = true; },
  };
}
