const BASE_URL = import.meta.env.VITE_EE_API_BASE ?? "/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) },
    ...options,
  });

  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json() as { detail?: string };
      if (body.detail) message = `${message}: ${body.detail}`;
    } catch {
      const text = await res.text().catch(() => "");
      if (text) message = `${message}: ${text}`;
    }
    throw new Error(message);
  }

  return res.json() as Promise<T>;
}

export const api = { request };
