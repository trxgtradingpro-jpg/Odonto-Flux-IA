const DIRECT_RENDER_API_BASE = "https://odontoflux-api.onrender.com/api/v1";
const DIRECT_API_HOSTNAMES = new Set(["clinicfluxai.com.br", "www.clinicfluxai.com.br"]);

function resolvePublicApiBase(): string {
  const configuredBase = process.env.NEXT_PUBLIC_API_URL;

  if (typeof window !== "undefined" && DIRECT_API_HOSTNAMES.has(window.location.hostname.toLowerCase())) {
    return configuredBase || DIRECT_RENDER_API_BASE;
  }

  if (typeof window !== "undefined" && window.location.hostname.endsWith(".onrender.com")) {
    const apiHost = window.location.hostname.replace("-web.", "-api.");
    if (apiHost !== window.location.hostname) {
      return `https://${apiHost}/api/v1`;
    }
  }

  return configuredBase || "/api/v1";
}

type PublicApiFetchOptions = {
  publicAccessToken?: string | null;
};

export async function publicApiFetch<T>(
  path: string,
  init?: RequestInit,
  options?: PublicApiFetchOptions,
): Promise<T> {
  const response = await fetch(`${resolvePublicApiBase()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(options?.publicAccessToken ? { "X-Link-Flow-Token": options.publicAccessToken } : {}),
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let message = "Nao foi possivel carregar o atendimento agora.";
    try {
      const payload = (await response.json()) as { error?: { message?: string } };
      message = payload.error?.message || message;
    } catch {
      // The public page only needs a safe, human-readable failure.
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}
