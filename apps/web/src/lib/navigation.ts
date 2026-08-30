/** Security boundary for query-string driven internal navigation. */

export function resolveJoinReturnTo(
  requested: string | null,
  festivalId: string,
  origin: string,
): string | null {
  if (!requested || requested.includes('\\') || /[\u0000-\u001f\u007f]/.test(requested)) {
    return null;
  }

  try {
    const base = new URL(origin);
    const destination = new URL(requested, base);
    const requiredPrefix = `/join/${encodeURIComponent(festivalId)}/`;

    if (destination.origin !== base.origin || !destination.pathname.startsWith(requiredPrefix)) {
      return null;
    }

    return `${destination.pathname}${destination.search}${destination.hash}`;
  } catch {
    return null;
  }
}
