import { host } from './host-v017.mjs';
import { makeJob, routeRef, draftRef, selectContext, roundLimit } from './protocol.mjs';
import { CouncilController } from './controller.mjs';
import { createPromoter, afterPromotion } from './draft.mjs';
import { createStorage } from './storage.mjs';
import { reasoningControls, setReasoningChoice, selectedReasoningLabel } from './effort.mjs';

const storage = createStorage(indexedDB);
const promote = createPromoter({ host });
// A chat route gives the chat; a new-chat draft gives its future chat plus the draft id.
function locate() {
  const chat = routeRef(window.location);
  if (chat) return chat;
  const draftRoute = draftRef(window.location);
  const session = draftRoute && host.draft.session(draftRoute.draftId);
  return session ? { environmentId: session.environmentId, threadId: session.threadId, projectId: session.projectId, draftId: draftRoute.draftId } : null;
}
const draftModel = (ref) => { const c = host.draft.composer(ref.draftId); return c?.modelSelectionByProvider?.[c?.activeProvider]?.model; };
const mount = document.createElement('div');
mount.id = 't3-adds-model-council';
const root = mount.attachShadow({ mode: 'open' });
document.body.append(mount);
const style = document.createElement('style');
style.textContent = `
  :host{font:13px/1.5 system-ui,sans-serif;color:var(--foreground,#eee)}
  *{box-sizing:border-box}button,input,textarea,select{font:inherit}button,a{touch-action:manipulation}
  button{cursor:pointer;flex-shrink:0;border:1px solid #8884;border-radius:9px;background:transparent;color:inherit;padding:9px 14px;transition:background .15s,border-color .15s}
  button:hover{background:color-mix(in srgb,var(--foreground,#fff) 7%,transparent);border-color:#8888}button:disabled{opacity:.45;cursor:default}
  button:focus-visible,a:focus-visible,summary:focus-visible{outline:2px solid #9b8cff;outline-offset:3px}
  #launch{display:inline-flex;gap:6px;align-items:center;white-space:nowrap;font-size:12px;padding:6px 8px;border-color:transparent;background:transparent;box-shadow:none}
  #launch[hidden]{display:none}
  dialog{padding:0;border:1px solid #8884;border-radius:20px;width:min(780px,calc(100vw - 32px));max-height:88vh;max-height:88dvh;background:var(--background,#18181b);color:inherit;box-shadow:0 24px 90px #0008;overflow:hidden}
  dialog[open]{display:flex;flex-direction:column}dialog::backdrop{background:#0009;backdrop-filter:blur(5px)}
  header,footer{flex-shrink:0;padding:20px 28px;display:flex;align-items:center;justify-content:space-between;gap:16px}
  header{border-bottom:1px solid #8883}footer{border-top:1px solid #8883;background:color-mix(in srgb,var(--foreground,#fff) 2%,transparent)}
  h2{font-size:19px;letter-spacing:-.4px;margin:0}h3{font-size:14px;font-weight:650;margin:0}h4{margin:18px 0 8px}
  main{padding:26px 28px;overflow:auto;min-height:0;scrollbar-gutter:stable;overscroll-behavior:contain}
  p{line-height:1.65;margin:0}.muted{color:color-mix(in srgb,var(--foreground,#eee) 65%,transparent)}.error{color:#ef9999;white-space:pre-wrap;overflow-wrap:anywhere;margin:12px 0}
  .intro{display:grid;gap:12px;margin-bottom:28px}.final-model{font-size:12px;overflow-wrap:anywhere}.final-model span{display:inline-block;border:1px solid #8883;border-radius:6px;padding:3px 8px;margin-left:6px;color:var(--foreground,#eee)}
  input[type=number],textarea,select{width:100%;min-width:0;background:color-mix(in srgb,var(--foreground,#fff) 3%,var(--background,#18181b));color:inherit;border:1px solid #8885;border-radius:10px;padding:11px 12px;outline:none}
  input:focus,textarea:focus,select:focus{border-color:#9b8cff;box-shadow:0 0 0 3px #9b8cff20}select option{background:var(--background,#18181b);color:var(--foreground,#eee)}
  textarea{resize:vertical;min-height:112px}label{display:grid;gap:9px;font-weight:550;margin:0}small{display:block;font-size:12px;line-height:1.65;font-weight:400}
  .question-field{margin-bottom:20px}.rounds-field{display:grid;grid-template-columns:minmax(0,1fr) 88px;gap:8px 24px;align-items:center;padding:18px 20px;border:1px solid #8883;border-radius:12px}.rounds-field input{grid-column:2;grid-row:1 / 3;text-align:center}.rounds-field small{grid-column:1}
  .section{margin-top:30px}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px}.badge{font-size:11px;font-weight:600;padding:3px 9px;border:1px solid #9b8cff40;background:#9b8cff12;border-radius:20px;color:#b8adff}
  .member-list{display:grid;gap:14px}.model{display:grid;gap:18px;padding:20px;border:1px solid #8884;border-radius:14px;background:color-mix(in srgb,var(--foreground,#fff) 2%,transparent)}
  .member-heading{display:flex;align-items:center;justify-content:space-between;gap:20px}.member-identity{min-width:0}.member-provider{font-size:11px;font-weight:600;letter-spacing:.5px;color:color-mix(in srgb,var(--foreground,#eee) 60%,transparent)}.member-name{font-size:14px;font-weight:600;margin-top:4px;overflow-wrap:anywhere}
  .remove{font-size:12px;padding:7px 11px;color:color-mix(in srgb,var(--foreground,#eee) 72%,transparent)}.effort-controls{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr));gap:16px;padding-top:16px;border-top:1px solid #8882}.effort-controls label{font-size:12px;font-weight:500;gap:8px}
  .catalog{padding:20px;border:1px solid #8883;border-radius:14px}.catalog>summary{font-size:14px;font-weight:600;cursor:pointer}.provider-list{display:grid;gap:20px;margin-top:20px}.provider{margin-bottom:9px;font-size:12px;font-weight:600}.provider-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center}
  .primary{background:#7560e8;color:#fff;border-color:#8975f0;font-weight:600;padding:11px 20px;box-shadow:0 3px 12px #0002}.primary:hover{background:#826df0;border-color:#a294ff}
  .usage-note{margin-top:24px;padding:16px 18px;border-radius:10px;background:color-mix(in srgb,var(--foreground,#fff) 3%,transparent)}.selection-count{font-size:12px;line-height:1.6;color:color-mix(in srgb,var(--foreground,#eee) 70%,transparent)}
  .job{border:1px solid #8884;border-radius:14px;padding:20px;margin-top:20px}.job>p{margin-top:12px}.job>small{margin-top:10px}.row{display:flex;gap:14px;align-items:center;justify-content:space-between}.stage{font-weight:600}details{margin-top:16px}summary{cursor:pointer;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.65 system-ui;margin:10px 0;max-height:240px;overflow:auto}a{color:#b8adff}.empty{padding:24px 18px;text-align:center;border:1px dashed #8884;border-radius:12px;font-size:12px;color:color-mix(in srgb,var(--foreground,#eee) 60%,transparent)}
  @media(max-width:600px){#launch{font-size:0;padding:6px}#launch::before{content:'◈';font-size:16px}dialog{width:calc(100vw - 20px);max-height:92dvh;border-radius:16px}header,footer{padding:16px 18px}main{padding:22px 18px}.model,.catalog{padding:16px}.rounds-field{padding:16px;gap:8px 16px}.member-heading{gap:12px}footer{flex-wrap:wrap}footer .primary{margin-left:auto}.section{margin-top:26px}}

`;
root.append(style);
const el = (tag, text, attrs = {}) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
};
const launch = el('button', '◈ Model Council', { id: 'launch', type: 'button', 'aria-label': 'Open Model Council' });
launch.hidden = true;
launch.title = 'Model Council';
const launcherMount = document.createElement('span');
launcherMount.id = 't3-adds-council-composer';
launcherMount.style.cssText = 'display:inline-flex;flex-shrink:0;align-items:center';
launcherMount.attachShadow({ mode: 'open' }).append(style.cloneNode(true), launch);
const dialog = el('dialog', undefined, { 'aria-labelledby': 'council-title' });
const header = el('header');
header.append(el('h2', 'Model Council', { id: 'council-title' }));
const close = el('button', 'Close', { type: 'button' });
close.onclick = () => dialog.close(); header.append(close);
const main = el('main'), footer = el('footer');
dialog.append(header, main, footer); root.append(dialog);
let currentRef = null, jobs = [], draft = '', selections = new Map(), loading = false, uiError = null, maxRoundsDraft = '2', catalogOpen = true;
let startButton;
const busyStages = new Set(['opinions', 'reviews', 'synthesis']);
const stageNames = { opinions: 'Preparing independent opinions', reviews: 'Peer review', synthesis: 'Preparing final answer', ready: 'Ready · waiting for the main chat to become idle', completed: 'Completed', cancelled: 'Stopped', failed: 'Failed' };

const controller = new CouncilController({ host, storage, changed(job) {
  const index = jobs.findIndex((j) => j.id === job.id);
  if (index === -1) jobs.push(job); else jobs[index] = job;
  updateLaunch(); renderJobs();
  if (startButton) startButton.disabled = loading || selections.size < 2 || !currentRef || !host.canOperate(currentRef) || relevantJobs().some((j) => busyStages.has(j.stage) || j.stage === 'ready');
} });

async function runWithLock(job, newRequest = false) {
  if (!navigator.locks) throw new Error('This browser does not support Web Locks, which Model Council needs to coordinate runs safely.');
  await navigator.locks.request(`t3-adds:council:${job.ref.environmentId}:${job.ref.threadId}`, { ifAvailable: true }, async (lock) => {
    if (!lock) {
      uiError = 'A council for this chat is already running in another window.';
      if (newRequest) { job.stage = 'failed'; job.error = uiError; await controller.persist(job); }
      render(); return;
    }
    const latest = await storage.get(job.id);
    if (latest && !busyStages.has(latest.stage) && !latest.cleanupPending) return;
    await controller.start(latest ?? job);
  });
}

function updateLaunch() {
  const ref = locate();
  const parent = ref && (ref.draftId ? ref : host.parent(ref));
  const composerFooter = [...document.querySelectorAll('[data-chat-composer-form="true"] [data-chat-composer-footer="true"]')]
    .find((node) => node.getClientRects().length > 0);
  if (parent && composerFooter) {
    if (launcherMount.parentElement !== composerFooter) {
      composerFooter.insertBefore(launcherMount, composerFooter.querySelector('[data-chat-composer-actions="right"]'));
    }
  } else launcherMount.remove();
  launch.hidden = !parent;
  const active = ref && jobs.find((j) => j.ref.environmentId === ref.environmentId && j.ref.threadId === ref.threadId && busyStages.has(j.stage));
  launch.textContent = active ? '◈ Council running' : '◈ Model Council';
}

function relevantJobs() {
  return currentRef ? jobs.filter((j) => j.ref.threadId === currentRef.threadId && j.ref.environmentId === currentRef.environmentId).sort((a, b) => b.createdAt.localeCompare(a.createdAt)) : [];
}

let jobsArea;
function renderJobs() {
  if (!jobsArea || !dialog.open) return;
  jobsArea.replaceChildren();
  for (const job of relevantJobs()) {
    const card = el('section', undefined, { class: 'job' });
    const row = el('div', undefined, { class: 'row' });
    row.append(el('span', (stageNames[job.stage] ?? job.stage) + (job.stage === 'reviews' ? ` · Round ${job.round ?? 2}/${job.maxRounds ?? 2}` : ''), { class: 'stage', role: 'status' }));
    if (busyStages.has(job.stage) || job.stage === 'ready') {
      const stop = el('button', 'Stop');
      stop.onclick = async () => { stop.disabled = true; try { await controller.cancel(job); } catch (e) { uiError = e.message; render(); } };
      row.append(stop);
    }
    card.append(row, el('p', job.question));
    if (job.stopReason) card.append(el('small', `${job.roundsCompleted} rounds completed · ${job.stopReason === 'members-finished' ? 'All remaining members finished debating' : job.stopReason === 'members-unavailable' ? 'No available members remain' : 'Maximum rounds reached'}`, { class: 'muted' }));
    if (job.error) card.append(el('p', job.error, { class: 'error' }));
    if (job.stage === 'ready') {
      const send = el('button', 'Send final answer to chat', { class: 'primary' });
      send.onclick = async () => { send.disabled = true; try { await controller.finish(job); } catch (e) { uiError = e.message; render(); } };
      card.append(send);
    }
    for (const member of job.members) {
      const detail = el('details'), summary = el('summary', `${member.label} · ${member.error ? 'Error' : member.done ? 'Finished debating' : member.review ? 'Review complete' : member.opinion ? 'Opinion ready' : 'Waiting'}`);
      detail.append(summary);
      if (member.created) detail.append(el('a', 'Open member chat', { href: host.href({ ...job.ref, threadId: member.threadId }) }));
      if (member.error) detail.append(el('p', member.error, { class: 'error' }));
      if (member.stopError) detail.append(el('p', `Could not confirm cancellation: ${member.stopError}`, { class: 'error' }));
      if (member.settleError) detail.append(el('p', `Could not settle member chat: ${member.settleError}`, { class: 'error' }));
      if (member.settled) detail.append(el('small', 'Member chat settled', { class: 'muted' }));
      if (member.opinion) detail.append(el('h4', 'Independent opinion'), el('pre', member.opinion.text));
      if (member.reviews?.length) {
        for (const turn of member.reviews.filter((r) => r.response)) detail.append(el('h4', `Round ${turn.round}${turn.response.done ? ' · Finished debating' : ''}`), el('pre', turn.response.text));
      } else if (member.review) detail.append(el('h4', 'Peer review'), el('pre', member.review.text));
      card.append(detail);
    }
    jobsArea.append(card);
  }
}

function render() {
  if (!currentRef) return;
  main.replaceChildren(); footer.replaceChildren();
  const parent = currentRef.draftId ? null : host.parent(currentRef);
  const intro = el('div', undefined, { class: 'intro' });
  intro.append(el('p', 'Independent perspectives, thoughtful discussion, one final answer.', { class: 'muted' }));
  const finalModel = el('p', 'Final answer by', { class: 'final-model muted' });
  finalModel.append(el('span', (currentRef.draftId ? draftModel(currentRef) : parent?.modelSelection?.model) ?? '—'));
  intro.append(finalModel); main.append(intro);
  if (uiError) main.append(el('p', uiError, { class: 'error', role: 'alert' }));
  const label = el('label', 'Ask the council', { class: 'question-field' });
  const question = el('textarea', undefined, { placeholder: 'What would you like the models to evaluate together?', 'aria-label': 'Council question' });
  question.value = draft;
  question.oninput = () => { draft = question.value; };
  label.append(question); main.append(label);
  const roundsLabel = el('label', 'Maximum rounds', { class: 'rounds-field' });
  const rounds = el('input', undefined, { type: 'number', min: '2', step: '1', required: '', 'aria-label': 'Maximum rounds' });
  rounds.value = maxRoundsDraft;
  rounds.oninput = () => { maxRoundsDraft = rounds.value; };
  roundsLabel.append(rounds, el('small', 'Includes the first independent opinion. The final answer is separate. Members may finish early.', { class: 'muted' }));
  main.append(roundsLabel);
  const providers = host.providers(currentRef);
  const count = el('span', `${selections.size} of 5 models selected · minimum 2`, { class: 'selection-count' });
  const selectedSection = el('section', undefined, { class: 'section', 'aria-labelledby': 'selected-models-title' });
  const selectedHeading = el('div', undefined, { class: 'section-heading' });
  selectedHeading.append(el('h3', 'Council members', { id: 'selected-models-title' }), el('span', `${selections.size} / 5`, { class: 'badge' }));
  const memberList = el('div', undefined, { class: 'member-list' });
  selectedSection.append(selectedHeading, memberList); main.append(selectedSection);
  if (!selections.size) memberList.append(el('div', 'Add at least two models below to form your council.', { class: 'empty' }));
  const catalog = el('details', undefined, { class: 'section catalog' });
  catalog.open = catalogOpen;
  catalog.ontoggle = () => { if (catalog.isConnected) catalogOpen = catalog.open; };
  catalog.append(el('summary', 'Add models'));
  const providerList = el('div', undefined, { class: 'provider-list' });
  catalog.append(providerList); main.append(catalog);
  for (const provider of providers) {
    const models = provider.models.filter((m) => !m.isLegacy);
    if (!models.length) continue;
    const providerGroup = el('div');
    providerGroup.append(el('div', provider.displayName ?? provider.driver, { class: 'provider' }));
    // A select keeps large provider catalogs usable without hiding models.
    const row = el('div', undefined, { class: 'provider-row' });
    const select = el('select', undefined, { 'aria-label': `${provider.displayName ?? provider.driver} model` });
    for (const model of models) select.append(el('option', model.name, { value: model.slug }));
    const add = el('button', 'Add');
    add.disabled = selections.size >= 5;
    add.onclick = () => {
      if (selections.size >= 5) return;
      const model = models.find((m) => m.slug === select.value);
      const key = `${provider.instanceId}:${model.slug}`;
      selections.set(key, { label: `${provider.displayName ?? provider.driver} / ${model.name}`, selection: { instanceId: provider.instanceId, model: model.slug } });
      render();
    };
    row.append(select, add); providerGroup.append(row); providerList.append(providerGroup);
  }
  for (const [key, member] of selections) {
    const row = el('div', undefined, { class: 'model' });
    const model = providers.find((p) => p.instanceId === member.selection.instanceId)?.models.find((m) => m.slug === member.selection.model);
    const remove = el('button', 'Remove', { class: 'remove', 'aria-label': `${member.label} remove` });
    remove.onclick = () => { selections.delete(key); render(); };
    const identity = el('div', undefined, { class: 'member-identity' });
    const provider = providers.find((p) => p.instanceId === member.selection.instanceId);
    identity.append(el('div', provider?.displayName ?? provider?.driver ?? member.selection.instanceId, { class: 'member-provider' }), el('div', model?.name ?? member.selection.model, { class: 'member-name' }));
    const heading = el('div', undefined, { class: 'member-heading' });
    heading.append(identity, remove); row.append(heading);
    const effortControls = el('div', undefined, { class: 'effort-controls' });
    const controls = reasoningControls(model);
    for (const control of controls) {
      const label = el('label', control.label);
      const effort = el('select', undefined, { 'aria-label': `${member.label} ${control.label}` });
      effort.append(el('option', control.defaultLabel ? `Default (${control.defaultLabel})` : 'Default', { value: '' }));
      for (const choice of control.choices) effort.append(el('option', choice.label, { value: choice.id }));
      const value = member.selection.options?.find((o) => o.id === control.id)?.value;
      effort.value = control.choices.find((c) => c.value === value)?.id ?? '';
      effort.onchange = () => { member.selection = setReasoningChoice(member.selection, control, effort.value); };
      label.append(effort); effortControls.append(label);
    }
    if (controls.length) row.append(effortControls);
    if (!controls.length) row.append(el('small', 'This model does not offer a separate thinking effort setting.', { class: 'muted' }));
    memberList.append(row);
  }
  if (!providers.length) main.append(el('p', 'No available providers were found in this environment.', { class: 'error' }));
  main.append(el('small', 'Members run up to your round limit and can finish early. Their chats settle automatically when the council ends; the final answer uses one additional turn. Long histories are selected within a budget. Members can retrieve older records when needed.', { class: 'muted usage-note' }));
  jobsArea = el('div'); main.append(jobsArea); renderJobs();
  const start = el('button', loading ? 'Preparing…' : 'Start council', { class: 'primary' });
  startButton = start;
  start.disabled = loading || selections.size < 2 || !host.canOperate(currentRef) || relevantJobs().some((j) => busyStages.has(j.stage) || j.stage === 'ready');
  start.onclick = async () => {
    loading = true; uiError = null; render();
    try {
      const maxRounds = roundLimit(Number(maxRoundsDraft));
      if (!navigator.locks) throw new Error('Web Locks support is required.');
      const wasDraft = Boolean(currentRef.draftId);
      const members = [...selections.values()].map((member) => {
        const model = providers.find((p) => p.instanceId === member.selection.instanceId)?.models.find((m) => m.slug === member.selection.model);
        const effort = selectedReasoningLabel(model, member.selection);
        return { ...member, label: member.label + (effort ? ` · ${effort}` : '') };
      });
      const prepare = async () => {
        const ref = { environmentId: currentRef.environmentId, threadId: currentRef.threadId }, parent = host.parent(ref);
        if (!parent || ['preparing', 'queued', 'starting', 'running', 'waiting'].includes(parent.status)) throw new Error('Wait for the current chat turn to finish before starting a council.');
        // A draft has no history yet: the question is the user's idea.
        const context = selectContext(wasDraft ? { threadId: ref.threadId, items: [] } : await host.transcript(ref));
        return makeJob({ ref, parent, question: draft, members, context, maxRounds });
      };
      let job;
      if (wasDraft) {
        // Validate everything that does not need the real chat before creating it.
        makeJob({ ref: currentRef, parent: { modelSelection: {} }, question: draft, members, context: { text: '' }, maxRounds });
        const promoted = await promote(currentRef.draftId);
        currentRef = { ...promoted, projectId: currentRef.projectId };
        job = await afterPromotion(async () => { const made = await prepare(); await controller.persist(made); return made; });
      } else {
        job = await prepare();
        await controller.persist(job);
      }
      draft = ''; void runWithLock(job, true).catch((e) => { uiError = e.message; render(); });
    } catch (e) { uiError = e.message; }
    finally { loading = false; render(); updateLaunch(); }
  };
  footer.append(count, start);
}

launch.onclick = async () => {
  currentRef = locate();
  if (!currentRef || (!currentRef.draftId && !host.parent(currentRef))) return;
  if (currentRef.draftId && !draft.trim()) draft = (host.draft.composer(currentRef.draftId)?.prompt ?? '').trim();
  try { jobs = await storage.all(); uiError = null; }
  catch (error) { uiError = error.message; }
  render(); dialog.showModal(); renderJobs();
};
window.addEventListener('hashchange', updateLaunch);
window.addEventListener('popstate', updateLaunch);
// T3 switches browser routes with pushState; the observer only updates our launcher.
let scheduled = false;
new MutationObserver(() => {
  if (scheduled) return;
  scheduled = true; requestAnimationFrame(() => { scheduled = false; updateLaunch(); });
}).observe(document.getElementById('root') ?? document.body, { childList: true, subtree: true });

try {
  jobs = await storage.all(); updateLaunch();
  for (const job of jobs.filter((j) => busyStages.has(j.stage) || j.cleanupPending)) {
    void runWithLock(job).catch((error) => { uiError = error.message; render(); });
  }
} catch (error) {
  console.error('[Model Council]', error); launch.title = error.message;
}
