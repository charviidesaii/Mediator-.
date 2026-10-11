import type {
  AlignmentWorkflowResult,
  ConfirmedDecision,
  DecisionActionRequest,
  MemberResponse,
  MemberResponseSubmit,
  Project,
  ProjectCreate,
  SynthesisReport,
  TeamMember,
  TeamMemberCreate,
} from "./models";

const rawBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
const rawMode = (import.meta.env.VITE_APP_MODE || import.meta.env.MODE || "").toLowerCase();
export const isMockMode = rawMode === "mock" || Boolean(rawBaseUrl && rawBaseUrl.includes("beeceptor.com"));

// Configurable HTTPS or localhost base URL:
// 1. Explicit VITE_API_BASE_URL (supports deployment HTTPS URLs)
// 2. Fallback based on mode (Beeceptor for mock mode, relative origin "" for live mode)
export const API_BASE_URL = rawBaseUrl && rawBaseUrl !== ""
  ? rawBaseUrl.replace(/\/$/, "")
  : (isMockMode ? "https://mediator.free.beeceptor.com" : "");

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

/**
 * Strips secrets, tokens, and masks personal emails to ensure Beeceptor public mock
 * receives strictly sanitized or synthetic test data.
 */
export function sanitizeMockPayload(data: unknown): unknown {
  if (typeof data === "string") {
    return data
      .replace(/([a-zA-Z0-9_\-\.]+)@([a-zA-Z0-9_\-\.]+)/g, "synthetic_user@example.test")
      .replace(/(?:xox[baprs]|sk-|ghp_|Bearer\s+)[a-zA-Z0-9_\-]+/gi, "[redacted_token]");
  }
  if (Array.isArray(data)) {
    return data.map(sanitizeMockPayload);
  }
  if (typeof data === "object" && data !== null) {
    const sanitized: Record<string, unknown> = {};
    for (const [key, val] of Object.entries(data)) {
      const lowerKey = key.toLowerCase();
      if (lowerKey.includes("token") || lowerKey.includes("secret") || lowerKey.includes("password") || lowerKey.includes("key")) {
        sanitized[key] = "[redacted_mock_secret]";
      } else {
        sanitized[key] = sanitizeMockPayload(val);
      }
    }
    return sanitized;
  }
  return data;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = `${API_BASE_URL}${normalizedPath}`;

  // Sanitize data and remove credentials if sending to Beeceptor mock mode
  const outgoingBody = isMockMode && options.body !== undefined
    ? sanitizeMockPayload(options.body)
    : options.body;

  const requestHeaders: Record<string, string> = {
    Accept: "application/json",
    ...(outgoingBody === undefined ? {} : { "Content-Type": "application/json" }),
    ...((options.headers as Record<string, string>) || {}),
  };

  if (isMockMode) {
    delete requestHeaders["Authorization"];
    delete requestHeaders["X-API-Key"];
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers: requestHeaders,
      body: outgoingBody === undefined ? undefined : JSON.stringify(outgoingBody),
    });
  } catch (err) {
    throw new ApiError(
      `Network connection failed to ${url}. Ensure the FastAPI backend is running on port 8000.`,
      0,
      err,
    );
  }

  const contentType = response.headers.get("content-type");
  const payload = contentType?.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`;
    if (typeof payload === "object" && payload !== null) {
      if ("detail" in payload) {
        message = String(payload.detail);
      } else if ("error" in payload) {
        message = String(payload.error);
      }
    }
    throw new ApiError(message, response.status, payload);
  }

  if (!contentType?.includes("application/json")) {
    throw new ApiError(
      typeof payload === "string" && payload.includes("nothing is configured")
        ? `Beeceptor route not configured: ${normalizedPath}`
        : `Expected JSON response from ${url} but received plain text.`,
      response.status,
      payload,
    );
  }

  return payload as T;
}

export const apiClient = {
  baseUrl: API_BASE_URL,
  appMode: isMockMode ? ("mock" as const) : ("live" as const),
  isMock: isMockMode,
  isConfigured: true,
  request,

  // Projects
  getProjects: () => request<Project[]>("/api/projects"),
  createProject: (data: ProjectCreate) =>
    request<Project>("/api/projects", { method: "POST", body: data }),
  getProject: (projectId: string) =>
    request<Project>(`/api/projects/${projectId}`),

  // Members
  addTeamMember: (projectId: string, data: TeamMemberCreate) =>
    request<TeamMember>(`/api/projects/${projectId}/members`, {
      method: "POST",
      body: data,
    }),

  // Responses / Check-ins
  submitResponse: (projectId: string, data: MemberResponseSubmit) =>
    request<MemberResponse>(`/api/projects/${projectId}/responses`, {
      method: "POST",
      body: data,
    }),
  getResponses: (projectId: string) =>
    request<MemberResponse[]>(`/api/projects/${projectId}/responses`),

  // Multi-Agent Analysis
  runAnalysis: (projectId: string) =>
    request<AlignmentWorkflowResult>(`/api/projects/${projectId}/analyze`, {
      method: "POST",
    }),
  getAlignmentReport: (projectId: string) =>
    request<SynthesisReport>(`/api/projects/${projectId}/alignment`),

  // Decisions
  recordDecision: (projectId: string, data: DecisionActionRequest) =>
    request<ConfirmedDecision>(`/api/projects/${projectId}/decisions`, {
      method: "POST",
      body: data,
    }),
  getDecisions: (projectId: string) =>
    request<ConfirmedDecision[]>(`/api/projects/${projectId}/decisions`),

  // Health
  getHealth: () => request<{ status: string; model: string }>("/health"),
};
