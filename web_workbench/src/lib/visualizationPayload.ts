export type Vector3 = [number, number, number]

export type VisualizationComponent = {
  id: string
  name: string
  shape: string
  material: string
  role?: string
  size: Vector3
  position: Vector3
  rotation: Vector3
  color?: string
  opacity: number
}

export type VisualizationTrack = {
  eventId: number
  trackId: number
  particle: string
  energyMeV: number
  points: Vector3[]
}

export type VisualizationDeposit = {
  eventId: number
  trackId: number
  volume: string
  position: Vector3
  edepMeV: number
}

export type VisualizationPayload = {
  status: 'waiting' | 'partial' | 'ready'
  visualEvents: number
  components: VisualizationComponent[]
  tracks: VisualizationTrack[]
  deposits: VisualizationDeposit[]
  warnings: string[]
}

export const VISIBLE_PARTICLE_TRACK_LIMIT = 100

type RawRecord = Record<string, unknown>

function asRecord(value: unknown): RawRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as RawRecord) : {}
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function numberValue(value: unknown, fallback = 0): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function text(value: unknown, fallback = ''): string {
  const normalized = String(value ?? '').trim()
  return normalized || fallback
}

function vector(value: unknown, fallback: Vector3 = [0, 0, 0]): Vector3 {
  const row = asArray(value)
  if (row.length < 3) {
    return [...fallback]
  }
  return [
    numberValue(row[0], fallback[0]),
    numberValue(row[1], fallback[1]),
    numberValue(row[2], fallback[2]),
  ]
}

function normalizeStatus(value: unknown): VisualizationPayload['status'] {
  return value === 'ready' || value === 'partial' || value === 'waiting' ? value : 'waiting'
}

function normalizeComponent(value: unknown): VisualizationComponent | null {
  const row = asRecord(value)
  const id = text(row.id ?? row.component_id)
  if (!id) {
    return null
  }
  return {
    id,
    name: text(row.name ?? row.display_name, id),
    shape: text(row.shape ?? row.geometry_type, 'box'),
    material: text(row.material ?? row.material_id),
    role: text(row.role ?? row.component_type),
    size: vector(row.size_mm ?? row.size, [1, 1, 1]),
    position: vector(row.position_mm ?? row.position),
    rotation: vector(row.rotation_deg ?? row.rotation),
    color: text(row.color),
    opacity: Math.min(1, Math.max(0.05, numberValue(row.opacity, 0.38))),
  }
}

function normalizeTrack(value: unknown): VisualizationTrack | null {
  const row = asRecord(value)
  const points = asArray(row.points_mm ?? row.points)
    .map((point) => vector(point))
    .filter((point) => point.length === 3)
  if (points.length < 2) {
    return null
  }
  return {
    eventId: numberValue(row.event_id ?? row.EventID),
    trackId: numberValue(row.track_id),
    particle: text(row.particle, 'unknown'),
    energyMeV: numberValue(row.energy_MeV),
    points,
  }
}

function normalizeDeposit(value: unknown): VisualizationDeposit | null {
  const row = asRecord(value)
  const edepMeV = numberValue(row.edep_MeV)
  if (edepMeV <= 0) {
    return null
  }
  return {
    eventId: numberValue(row.event_id ?? row.EventID),
    trackId: numberValue(row.track_id),
    volume: text(row.volume),
    position: vector(row.position_mm ?? row.position),
    edepMeV,
  }
}

export function normalizeVisualizationPayload(value: unknown): VisualizationPayload {
  const row = asRecord(value)
  const source = asRecord(row.source)
  const geometry = asRecord(row.geometry)
  const components = asArray(geometry.components)
    .map(normalizeComponent)
    .filter((component): component is VisualizationComponent => Boolean(component))
  const tracks = asArray(row.tracks)
    .map(normalizeTrack)
    .filter((track): track is VisualizationTrack => Boolean(track))
  const deposits = asArray(row.deposits)
    .map(normalizeDeposit)
    .filter((deposit): deposit is VisualizationDeposit => Boolean(deposit))

  return {
    status: normalizeStatus(row.status),
    visualEvents: numberValue(source.visual_events ?? row.visualEvents, 100),
    components,
    tracks,
    deposits,
    warnings: asArray(row.warnings).map((item) => text(item)).filter(Boolean),
  }
}

export function layerStats(payload: VisualizationPayload, showParticles: boolean) {
  const visibleTracks = visibleParticleTracks(payload, showParticles)
  return {
    components: payload.components.length,
    tracks: visibleTracks.length,
    deposits: payload.deposits.length,
    visibleTrackPoints: visibleTracks.reduce((total, track) => total + track.points.length, 0),
  }
}

export function visibleParticleTracks(
  payload: VisualizationPayload,
  showParticles: boolean,
): VisualizationTrack[] {
  if (!showParticles) {
    return []
  }
  return payload.tracks.slice(0, VISIBLE_PARTICLE_TRACK_LIMIT)
}
