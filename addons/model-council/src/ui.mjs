import { host } from './host-v016.mjs';
import { makeJob, routeRef, selectContext } from './protocol.mjs';
import { CouncilController } from './controller.mjs';
import { createStorage } from './storage.mjs';
import { reasoningControls, setReasoningChoice, selectedReasoningLabel } from './effort.mjs';

const storage = createStorage(indexedDB);
const mount = document.createElement('div');
mount.id = 't3-adds-model-council';
const root = mount.attachShadow({ mode: 'open' });
document.body.append(mount);
const style = document.createElement('style');
style.textContent = `
  :host{font:13px system-ui,sans-serif;color:var(--foreground,#eee)}
  *{box-sizing:border-box}button,input,textarea,select{font:inherit}button,a{touch-action:manipulation}
  button{cursor:pointer;border:1px solid #7775;border-radius:8px;background:var(--background,#18181b);color:inherit;padding:8px 12px}
  button:hover{background:color-mix(in srgb,var(--foreground,#fff) 10%,var(--background,#18181b))}button:disabled{opacity:.5;cursor:default}
  #launch{display:inline-flex;gap:6px;align-items:center;white-space:nowrap;font-size:12px;padding:6px 8px;border-color:transparent;background:transparent;box-shadow:none}
  @media(max-width:600px){#launch{font-size:0;padding:6px}#launch::before{content:'◈';font-size:16px}}
  #launch[hidden]{display:none}dialog{padding:0;border:1px solid #8885;border-radius:16px;width:min(740px,calc(100vw - 32px));max-height:85vh;background:var(--background,#18181b);color:inherit;box-shadow:0 24px 90px #0007}
  dialog::backdrop{background:#0007}header,footer{padding:18px 22px;display:flex;align-items:center;justify-content:space-between;gap:12px}header{border-bottom:1px solid #8883}h2{font-size:18px;margin:0}main{padding:18px 22px;overflow:auto;max-height:calc(85vh - 155px)}p{line-height:1.55;margin:0 0 14px}.muted{opacity:.68}.error{color:#ef8888;white-space:pre-wrap}
  textarea,select{width:100%;background:var(--background,#18181b);color:inherit;border:1px solid #8886;border-radius:8px;padding:10px}textarea{resize:vertical;min-height:100px;margin-top:8px}label{display:block;margin-bottom:12px}.model{display:flex;align-items:center;gap:10px;border:1px solid #8883;padding:12px;border-radius:9px}.model input{margin:0}.provider{margin:18px 0 8px;font-weight:600}.primary{background:#6d5ce8;color:#fff;border-color:#6d5ce8}.job{border:1px solid #8884;border-radius:10px;padding:14px;margin-top:14px}.row{display:flex;gap:10px;align-items:center;justify-content:space-between}.stage{font-weight:600}details{margin-top:12px}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.55 system-ui;margin:10px 0;max-height:240px;overflow:auto}a{color:#a6a0ff}small{display:block;margin-top:6px}.empty{padding:20px;text-align:center;opacity:.6}
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
let currentRef = null, jobs = [], draft = '', selections = new Map(), loading = false, uiError = null;
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
    if (latest && !busyStages.has(latest.stage)) return;
    await controller.start(latest ?? job);
  });
}

function updateLaunch() {
  const ref = routeRef(window.location);
  const parent = ref && host.parent(ref);
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
    row.append(el('span', stageNames[job.stage] ?? job.stage, { class: 'stage', role: 'status' }));
    if (busyStages.has(job.stage) || job.stage === 'ready') {
      const stop = el('button', 'Stop');
      stop.onclick = async () => { stop.disabled = true; try { await controller.cancel(job); } catch (e) { uiError = e.message; render(); } };
      row.append(stop);
    }
    card.append(row, el('p', job.question));
    if (job.error) card.append(el('p', job.error, { class: 'error' }));
    if (job.stage === 'ready') {
      const send = el('button', 'Send final answer to chat', { class: 'primary' });
      send.onclick = async () => { send.disabled = true; try { await controller.finish(job); } catch (e) { uiError = e.message; render(); } };
      card.append(send);
    }
    for (const member of job.members) {
      const detail = el('details'), summary = el('summary', `${member.label} · ${member.error ? 'Error' : member.review ? 'Review complete' : member.opinion ? 'Opinion ready' : 'Waiting'}`);
      detail.append(summary);
      if (member.created) detail.append(el('a', 'Open member chat', { href: host.href({ ...job.ref, threadId: member.threadId }) }));
      if (member.error) detail.append(el('p', member.error, { class: 'error' }));
      if (member.stopError) detail.append(el('p', `Could not confirm cancellation: ${member.stopError}`, { class: 'error' }));
      if (member.opinion) detail.append(el('h4', 'Independent opinion'), el('pre', member.opinion.text));
      if (member.review) detail.append(el('h4', 'Peer review'), el('pre', member.review.text));
      card.append(detail);
    }
    jobsArea.append(card);
  }
}

function render() {
  if (!currentRef) return;
  main.replaceChildren(); footer.replaceChildren();
  const parent = host.parent(currentRef);
  main.append(el('p', 'Models independently review the same context, then evaluate each other’s opinions. The model selected in this chat presents one final answer.', { class: 'muted' }));
  main.append(el('p', `Final model: ${parent?.modelSelection?.model ?? '—'}`));
  if (uiError) main.append(el('p', uiError, { class: 'error', role: 'alert' }));
  const label = el('label', 'Ask the council');
  const question = el('textarea', undefined, { placeholder: 'What would you like the models to evaluate together?', 'aria-label': 'Council question' });
  question.value = draft;
  question.oninput = () => { draft = question.value; };
  label.append(question); main.append(label);
  const providers = host.providers(currentRef);
  const count = el('span', `${selections.size} models selected · choose 2–5`);
  for (const provider of providers) {
    const models = provider.models.filter((m) => !m.isLegacy);
    if (!models.length) continue;
    main.append(el('div', provider.displayName ?? provider.driver, { class: 'provider' }));
    // A select keeps large provider catalogs usable without hiding models.
    const row = el('div', undefined, { class: 'row' });
    const select = el('select', undefined, { 'aria-label': `${provider.displayName ?? provider.driver} model` });
    for (const model of models) select.append(el('option', model.name, { value: model.slug }));
    const add = el('button', 'Add');
    add.onclick = () => {
      if (selections.size >= 5) return;
      const model = models.find((m) => m.slug === select.value);
      const key = `${provider.instanceId}:${model.slug}`;
      selections.set(key, { label: `${provider.displayName ?? provider.driver} / ${model.name}`, selection: { instanceId: provider.instanceId, model: model.slug } });
      render();
    };
    row.append(select, add); main.append(row);
  }
  for (const [key, member] of selections) {
    const row = el('div', undefined, { class: 'model' });
    row.style.flexWrap = 'wrap';
    const model = providers.find((p) => p.instanceId === member.selection.instanceId)?.models.find((m) => m.slug === member.selection.model);
    const remove = el('button', 'Remove', { 'aria-label': `${member.label} remove` });
    remove.onclick = () => { selections.delete(key); render(); };
    row.append(el('span', member.label), remove);
    const controls = reasoningControls(model);
    for (const control of controls) {
      const label = el('label', `${control.label} / Thinking effort`);
      label.style.cssText = 'margin:0;flex:1 1 180px';
      const effort = el('select', undefined, { 'aria-label': `${member.label} ${control.label}` });
      effort.append(el('option', control.defaultLabel ? `Default (${control.defaultLabel})` : 'Default', { value: '' }));
      for (const choice of control.choices) effort.append(el('option', choice.label, { value: choice.id }));
      const value = member.selection.options?.find((o) => o.id === control.id)?.value;
      effort.value = control.choices.find((c) => c.value === value)?.id ?? '';
      effort.onchange = () => { member.selection = setReasoningChoice(member.selection, control, effort.value); };
      label.append(effort); row.append(label);
    }
    if (!controls.length) row.append(el('small', 'This model does not offer a separate thinking effort setting.', { class: 'muted' }));
    main.append(row);
  }
  if (!providers.length) main.append(el('p', 'No available providers were found in this environment.', { class: 'error' }));
  main.append(el('small', 'Each member runs two rounds; the final answer uses one additional round. Long histories are selected within a budget. Members can retrieve older records when needed.', { class: 'muted' }));
  jobsArea = el('div'); main.append(jobsArea); renderJobs();
  const start = el('button', loading ? 'Preparing…' : 'Start council', { class: 'primary' });
  startButton = start;
  start.disabled = loading || selections.size < 2 || !host.canOperate(currentRef) || relevantJobs().some((j) => busyStages.has(j.stage) || j.stage === 'ready');
  start.onclick = async () => {
    loading = true; uiError = null; render();
    try {
      if (!navigator.locks) throw new Error('Web Locks support is required.');
      const ref = { ...currentRef }, parent = host.parent(ref);
      if (!parent || ['preparing', 'queued', 'starting', 'running', 'waiting'].includes(parent.status)) throw new Error('Wait for the current chat turn to finish before starting a council.');
      const context = selectContext(await host.transcript(ref));
      const members = [...selections.values()].map((member) => {
        const model = providers.find((p) => p.instanceId === member.selection.instanceId)?.models.find((m) => m.slug === member.selection.model);
        const effort = selectedReasoningLabel(model, member.selection);
        return { ...member, label: member.label + (effort ? ` · ${effort}` : '') };
      });
      const job = makeJob({ ref, parent, question: draft, members, context });
      await controller.persist(job);
      draft = ''; void runWithLock(job, true).catch((e) => { uiError = e.message; render(); });
    } catch (e) { uiError = e.message; }
    finally { loading = false; render(); }
  };
  footer.append(count, start);
}

launch.onclick = async () => {
  currentRef = routeRef(window.location);
  if (!currentRef || !host.parent(currentRef)) return;
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
  for (const job of jobs.filter((j) => busyStages.has(j.stage))) {
    void runWithLock(job).catch((error) => { uiError = error.message; render(); });
  }
} catch (error) {
  console.error('[Model Council]', error); launch.title = error.message;
}
