import type {
  CollectionRun, DataResponse, ErrorResponse, HealthStatus, Item, ItemStats, PageResponse, SourceType,
} from './types.ts'

/*
 * Thin wrapper around fetch for calling the FastAPI backend.
 * The base URL comes from VITE_API_BASE_URL so local and Railway builds
 * can point at different backends without code changes.
 *
 * Every failed request throws an ApiError carrying the backend's error code and
 * its plain-language message, so components can show it to the user as-is.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// Error from the API (or from not reaching it at all), with a user-facing message
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly retryAfterSeconds: number | null

  constructor(status: number, code: string, message: string, retryAfterSeconds: number | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.retryAfterSeconds = retryAfterSeconds
  }
}

// Sends one request to the /v1 API and returns the parsed JSON body, or throws ApiError
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/v1${path}`, init)
  } catch {
    // Network failure: the backend isn't running or isn't reachable
    throw new ApiError(0, 'network_error', 'Could not reach the API. Check that the backend is running.')
  }

  if (!response.ok) {
    throw await toApiError(response)
  }
  return (await response.json()) as T
}

// Builds an ApiError from the backend's {"error": {...}} envelope, with a fallback if the body isn't one
async function toApiError(response: Response): Promise<ApiError> {
  const retryAfter = Number(response.headers.get('Retry-After'))
  const retryAfterSeconds = Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null
  try {
    const body = (await response.json()) as ErrorResponse
    if (body?.error?.message) {
      return new ApiError(response.status, body.error.code, body.error.message, retryAfterSeconds)
    }
  } catch {
    // Not JSON - fall through to the generic message
  }
  return new ApiError(response.status, 'unknown_error',
    `The API returned an unexpected error (status ${response.status}). Try again in a moment.`, retryAfterSeconds)
}

// Turns a filters object into a query string, leaving out empty values
function queryString(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

// ---------- Endpoints ----------

export const getHealth = () => request<DataResponse<HealthStatus>>('/health').then((body) => body.data)

export type ItemFilters = { sourceType?: SourceType; sourceName?: string; limit?: number; cursor?: string | null }

export const listItems = ({ sourceType, sourceName, limit = 20, cursor }: ItemFilters) =>
  request<PageResponse<Item>>(
    `/items${queryString({ source_type: sourceType, source_name: sourceName, limit, cursor })}`,
  )

export const getItemStats = (days: number) =>
  request<DataResponse<ItemStats>>(`/item-stats${queryString({ days })}`).then((body) => body.data)

// Resolves to null when no run has happened yet (the API answers 404 'no_runs')
export const getLatestRun = () =>
  request<DataResponse<CollectionRun>>('/collection-runs/latest')
    .then((body) => body.data)
    .catch((error: unknown) => {
      if (error instanceof ApiError && error.code === 'no_runs') return null
      throw error
    })

export const startRun = () =>
  request<DataResponse<CollectionRun>>('/collection-runs', { method: 'POST' }).then((body) => body.data)
