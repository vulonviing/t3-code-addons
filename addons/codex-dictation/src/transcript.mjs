// Only explicit user/input transcripts are accepted. Assistant speech is never inserted.
export function createTranscript() {
  const items = new Map();
  let frameless = false;
  return {
    accept(event) {
      if (event.type === 'input_transcript.added' && event.item?.type === 'input_transcript'
          && typeof event.item.id === 'string' && typeof event.item.text === 'string') {
        frameless = true;
        items.set(event.item.id, event.item.text);
      } else if (typeof event.item_id !== 'string') return null;
      else if (event.type === 'conversation.item.input_audio_transcription.completed' && typeof event.transcript === 'string') {
        items.set(event.item_id, event.transcript.trim());
      } else if (event.type === 'conversation.item.input_audio_transcription.delta' && typeof event.delta === 'string') {
        items.set(event.item_id, (items.get(event.item_id) ?? '') + event.delta);
      } else return null;
      return [...items.values()].filter(Boolean).join(frameless ? '' : '\n').trim();
    },
  };
}
