// All deployment settings come from environment variables (root .env locally, the host's env vars in production).
// VITE_* values are baked into the public bundle at build time: never put secrets in them.
const env = import.meta.env

// Backend base URL. Empty = same origin (the Vite dev proxy locally, or nginx in Docker).
export const BACKEND_URL = (env.VITE_BACKEND_URL ?? '').replace(/\/$/, '')

// Map basemap. Defaults to the free OpenStreetMap tiles.
export const TILE_URL = env.VITE_MAP_TILE_URL || 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
export const TILE_ATTRIBUTION = env.VITE_MAP_ATTRIBUTION || '&copy; OpenStreetMap contributors'
