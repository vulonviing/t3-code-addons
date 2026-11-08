export function view(snapshot) {
  return {
    resolved: snapshot.resolvedTheme === 'dark' ? 'dark' : 'light',
    following: snapshot.appearanceMode === 'system' || snapshot.followSystem === true,
  };
}

// Always pins an explicit mode, even when the clicked mode is already showing through "follow system".
export function choose(host, mode) {
  if (mode !== 'light' && mode !== 'dark') throw new Error(`Unsupported appearance mode: ${mode}`);
  if (host.setAppearanceMode(mode) !== true) throw new Error('T3 could not save the theme choice.');
}
