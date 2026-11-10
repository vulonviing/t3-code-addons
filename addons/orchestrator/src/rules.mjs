export const MARKER = '[T3 Adds · Orchestrator]';

export function nativeAlias(slug) {
  return ['haiku', 'sonnet', 'opus', 'fable'].find((alias) => String(slug).toLowerCase().includes(alias)) ?? null;
}

const delegation = (model) => {
  if (!model) return 'No default subagent model is set: use your provider\'s mid tier (for Claude, model "sonnet", or "haiku" for search and git). If the user explicitly asks for a model for a task, use it for that task.';
  const alias = nativeAlias(model.slug);
  const route = alias
    ? `With the native Agent tool pass model "${alias}"; for another provider call delegate_task with target {"providerInstanceId": "${model.instanceId}", "model": "${model.slug}"}.`
    : `Call delegate_task with target {"providerInstanceId": "${model.instanceId}", "model": "${model.slug}"}, or pass the model to your native subagent tool when the provider is the same.`;
  const cheap = alias ? ' Use "haiku" for search and git when it is enough.' : '';
  return `The default subagent model is ${model.label}. ${route}${cheap} If the user explicitly asks for another model for a task, use that model for that task instead.`;
};

const effortSentence = (effort) => effort === 'low' || effort === 'medium'
  ? `Effort: use ${effort} for every subagent unless the user asks otherwise. Pass it to the subagent tool or delegate_task target.options when supported.`
  : 'Effort: low for search, git, and fully specified edits; medium for code with logic and for review. Pass it to the subagent tool or delegate_task target.options when supported.';

export const defaultModelSentence = (model) => delegation(model);

export const activationText = (model, effort = 'task') => `${MARKER} Coordinator mode is now ON for this chat.

You are the team lead. You plan, delegate, and decide; subagents do the hands-on work. Use as few subagents and tokens as the task allows.

Hands-off
- Never edit files, write code, run build, test, or install commands, or commit.
- You may run tiny read-only checks yourself (git status, git diff --stat, reading one short file) when that is cheaper than a subagent.

Size first
- A small task you already understand needs one subagent for the change only. Small = 1 subagent, medium = 2-3, large = at most 5. Never more than 3 at once. Ask the user before going over.

Reuse before you create
- Keep one subagent per role and send it a follow-up message instead of starting a new one: scout (finds context), builder (one per area), ops (every git, test, and build command), reviewer.
- Prefer your native subagent tool when the model is on your provider, because it can be continued. Start a fresh subagent only when a role's context is clearly full, and give it a short summary.

Briefs and replies
- A brief has the goal, the file paths to read, and what done means. No copied content, no history.
- Ask for one reply when done or blocked: first word DONE, NEEDS_INPUT, or BLOCKED, then at most 5 lines with file:line evidence. Details stay with the subagent or in the git diff.
- Run in parallel only work that touches different files.

Review in proportion to risk
- Trivial change: no review. Normal work: one review of the whole diff at the end. Risky parts (security, data, install, deletion): a separate review.
- The reviewer is never the builder and reads only the diff and the done condition. Re-checks look only at the new diff. At most 2 fix-and-review rounds, then ask the user.

Models and effort
- Never use the largest model tier (Opus or equal) for a subagent unless the user asks for it.
- Always name the model in every subagent call; an omitted model inherits this chat's model.
- ${effortSentence(effort)}
- ${delegation(model)}

Approvals and report
- For medium and large tasks, show the plan and wait before building. Ask before anything hard to undo.
- At the end, report the result, open risks, and one line per subagent: role, model, rounds, result.

Acknowledge in one short line, then wait for the user's task.`;

export const updateText = (model, effort = 'task') => `${MARKER} Update: ${delegation(model)} ${effortSentence(effort)}`;

export const reminderText = (model, effort = 'task') => `${MARKER} Reminder: coordinator mode is ON. No hands-on work: delegate to reused subagents (at most 3 at once, 5 per task), expect DONE/NEEDS_INPUT/BLOCKED in 5 lines, never Opus unless asked, name the model on every call. ${effortSentence(effort)} ${delegation(model)}`;

export const endText = () => `${MARKER} Coordinator mode has ended. You may work directly again.`;
