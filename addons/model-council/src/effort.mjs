const REASONING_IDS = new Set(['reasoningEffort', 'effort', 'reasoning', 'variant', 'reasoning_effort', 'thinking_level', 'thinking']);

export function reasoningControls(model) {
  return (model?.capabilities?.optionDescriptors ?? []).filter((d) => d.role === 'reasoning' || REASONING_IDS.has(d.id)).flatMap((descriptor) => {
    const choices = descriptor.type === 'boolean'
      ? [{ id: 'true', label: 'On', value: true }, { id: 'false', label: 'Off', value: false }]
      : (descriptor.options ?? []).filter((o) => !descriptor.promptInjectedValues?.includes(o.id)).map((o) => ({ ...o, value: o.id }));
    if (!choices.length) return [];
    const defaultChoice = choices.find((c) => c.value === descriptor.currentValue) ?? choices.find((c) => c.isDefault);
    return [{ ...descriptor, choices, defaultLabel: defaultChoice?.label }];
  });
}

export function setReasoningChoice(selection, control, choiceId) {
  const options = (selection.options ?? []).filter((o) => o.id !== control.id);
  if (choiceId !== '') {
    const choice = control.choices.find((c) => c.id === choiceId);
    if (!choice) throw new Error('This thinking effort level is not supported by the model.');
    options.push({ id: control.id, value: choice.value });
  }
  const { options: _previous, ...base } = selection;
  return options.length ? { ...base, options } : base;
}

export function selectedReasoningLabel(model, selection) {
  return reasoningControls(model).flatMap((control) => {
    const value = selection.options?.find((o) => o.id === control.id)?.value;
    const choice = control.choices.find((c) => c.value === value);
    return choice ? [choice.label] : [];
  }).join(' / ');
}
