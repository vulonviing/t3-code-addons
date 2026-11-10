export function modelOptions(providers) {
  return providers.flatMap((provider) => provider.models.filter((m) => !m.isLegacy).map((m) => ({
    instanceId: provider.instanceId, slug: m.slug, label: `${provider.displayName ?? provider.driver} / ${m.name}`,
  })));
}

export function routeRef(location) {
  const path = location.hash?.startsWith('#/') ? location.hash.slice(1) : location.pathname;
  const parts = path.split('?')[0].split('/').filter(Boolean).map(decodeURIComponent);
  return parts.length === 2 && !['settings', 'draft', 'onboarding'].includes(parts[0])
    ? { environmentId: parts[0], threadId: parts[1] } : null;
}

export function draftRef(location) {
  const path = location.hash?.startsWith('#/') ? location.hash.slice(1) : location.pathname;
  const parts = path.split('?')[0].split('/').filter(Boolean).map(decodeURIComponent);
  return parts.length === 2 && parts[0] === 'draft' ? { draftId: parts[1] } : null;
}
