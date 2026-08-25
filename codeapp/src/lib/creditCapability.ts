export type CreditCapability = "unavailable" | "setup-required" | "ready";

export async function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => reject(new Error("Credit capability check timed out")), timeoutMs);
  });

  try {
    return await Promise.race([promise, timeout]);
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
  }
}

export function classifyCreditCapability(addonInstalled: boolean, hasSyncRun: boolean): CreditCapability {
  if (!addonInstalled) return "unavailable";
  return hasSyncRun ? "ready" : "setup-required";
}