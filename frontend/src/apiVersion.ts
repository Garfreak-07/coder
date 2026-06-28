export type CoderApiVersion = "v2" | "v3";

interface ApiVersionInput {
  env?: Record<string, unknown>;
  search?: string;
  localStorageValue?: string | null;
}

export function resolveCoderApiVersion(input: ApiVersionInput = {}): CoderApiVersion {
  const queryValue = apiVersionFromSearch(input.search);
  const raw =
    queryValue ??
    input.localStorageValue ??
    stringValue(input.env?.VITE_CODER_API_VERSION) ??
    stringValue(input.env?.CODER_USE_RUST_API);
  return normalizeApiVersion(raw);
}

export function shouldUseRustApiV3(): boolean {
  const env = (import.meta as ImportMeta & { env?: Record<string, unknown> }).env;
  const localStorageValue = readLocalStorageApiVersion();
  const search = typeof window === "undefined" ? "" : window.location.search;
  return resolveCoderApiVersion({ env, search, localStorageValue }) === "v3";
}

function apiVersionFromSearch(search: string | undefined): string | null {
  if (!search) return null;
  const params = new URLSearchParams(search);
  return params.get("coder_api_version") ?? params.get("api_version") ?? params.get("rust_api");
}

function readLocalStorageApiVersion(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem("coder_api_version");
  } catch {
    return null;
  }
}

function normalizeApiVersion(value: string | null | undefined): CoderApiVersion {
  const normalized = value?.trim().toLowerCase();
  if (normalized === "v3" || normalized === "3" || normalized === "rust" || normalized === "1" || normalized === "true") {
    return "v3";
  }
  return "v2";
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}
