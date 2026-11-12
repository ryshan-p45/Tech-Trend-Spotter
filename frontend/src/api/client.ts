/*
 * Thin wrapper around fetch for calling the FastAPI backend.
 * The base URL comes from VITE_API_BASE_URL so local and Railway builds
 * can point at different backends without code changes.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// Fetches a JSON resource from the /v1 API and throws a readable error on failure
export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/v1${path}`)

  if (!response.ok) {
    throw new Error(`Request to ${path} failed with status ${response.status}`)
  }

  return response.json() as Promise<T>
}

export type HealthResponse = { status: 'ok' }

export const getHealth = () => apiGet<HealthResponse>('/health')
