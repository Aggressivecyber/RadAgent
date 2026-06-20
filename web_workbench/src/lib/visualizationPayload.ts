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

export type VisualizationEnergyPoint = {
  x: number
  y: number
  z: number
  edepMeV: number
}

export type VisualizationParticleCount = {
  particle: string
  count: number
}

export type VisualizationSliceAxis = 'x' | 'y' | 'z'

export type VisualizationSliceHeatmap = {
  value: number
  xAxis: VisualizationSliceAxis
  yAxis: VisualizationSliceAxis
  x: number[]
  y: number[]
  z: number[][]
}

export type VisualizationSlicePlane = {
  axis: VisualizationSliceAxis
  values: number[]
  slices: VisualizationSliceHeatmap[]
}

export type VisualizationAnalysis = {
  source: 'full_run'
  stats: {
    trackCount: number
    depositCount: number
    totalEdepMeV: number
  }
  particleCounts: VisualizationParticleCount[]
  energyPoints: VisualizationEnergyPoint[]
  slicePlanes: Partial<Record<VisualizationSliceAxis, VisualizationSlicePlane>>
}

export type VisualizationSourceRay = {
  sourceId: string
  particle: string
  energy: Record<string, unknown>
  sourceShape: 'point' | 'circle' | 'rectangle'
  directionMode: 'mono' | 'gaussian' | 'custom' | 'random'
  sampleIndex: number
  sampleCount: number
  start: Vector3
  end: Vector3
}

export type VisualizationPayload = {
  status: 'waiting' | 'partial' | 'ready'
  visualEvents: number
  components: VisualizationComponent[]
  sourceRays: VisualizationSourceRay[]
  tracks: VisualizationTrack[]
  deposits: VisualizationDeposit[]
  analysis?: VisualizationAnalysis
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

function normalizeEnergyPoint(value: unknown): VisualizationEnergyPoint | null {
  const row = asRecord(value)
  const edepMeV = numberValue(row.edep_MeV ?? row.edepMeV)
  if (edepMeV <= 0) {
    return null
  }
  return {
    x: numberValue(row.x),
    y: numberValue(row.y),
    z: numberValue(row.z),
    edepMeV,
  }
}

function normalizeParticleCount(value: unknown): VisualizationParticleCount | null {
  const row = asRecord(value)
  const particle = text(row.particle, 'unknown')
  const count = numberValue(row.count)
  if (count <= 0) {
    return null
  }
  return { particle, count }
}

function normalizeSliceAxis(value: unknown, fallback: VisualizationSliceAxis): VisualizationSliceAxis {
  const normalized = text(value, fallback).toLowerCase()
  return normalized === 'x' || normalized === 'y' || normalized === 'z' ? normalized : fallback
}

function normalizeNumberArray(value: unknown): number[] {
  return asArray(value)
    .map((item) => numberValue(item, Number.NaN))
    .filter(Number.isFinite)
}

function normalizeHeatmapGrid(value: unknown): number[][] {
  return asArray(value)
    .map((row) => normalizeNumberArray(row))
    .filter((row) => row.length > 0)
}

function normalizeSliceHeatmap(value: unknown, axis: VisualizationSliceAxis): VisualizationSliceHeatmap | null {
  const row = asRecord(value)
  const axes = (['x', 'y', 'z'] as VisualizationSliceAxis[]).filter((item) => item !== axis)
  const z = normalizeHeatmapGrid(row.z)
  if (z.length === 0) {
    return null
  }
  return {
    value: numberValue(row.value),
    xAxis: normalizeSliceAxis(row.x_axis ?? row.xAxis, axes[0] ?? 'x'),
    yAxis: normalizeSliceAxis(row.y_axis ?? row.yAxis, axes[1] ?? 'y'),
    x: normalizeNumberArray(row.x),
    y: normalizeNumberArray(row.y),
    z,
  }
}

function normalizeSlicePlane(value: unknown, fallbackAxis: VisualizationSliceAxis): VisualizationSlicePlane | null {
  const row = asRecord(value)
  const axis = normalizeSliceAxis(row.axis, fallbackAxis)
  const slices = asArray(row.slices)
    .map((slice) => normalizeSliceHeatmap(slice, axis))
    .filter((slice): slice is VisualizationSliceHeatmap => Boolean(slice))
  if (slices.length === 0) {
    return null
  }
  const values = normalizeNumberArray(row.values)
  return {
    axis,
    values: values.length > 0 ? values : slices.map((slice) => slice.value),
    slices,
  }
}

function normalizeAnalysis(value: unknown): VisualizationAnalysis | undefined {
  const row = asRecord(value)
  if (Object.keys(row).length === 0) {
    return undefined
  }
  const stats = asRecord(row.stats)
  const rawSlicePlanes = asRecord(row.slice_planes ?? row.slicePlanes)
  const slicePlanes: VisualizationAnalysis['slicePlanes'] = {}
  for (const axis of ['x', 'y', 'z'] as VisualizationSliceAxis[]) {
    const plane = normalizeSlicePlane(rawSlicePlanes[axis], axis)
    if (plane) {
      slicePlanes[axis] = plane
    }
  }
  return {
    source: 'full_run',
    stats: {
      trackCount: numberValue(stats.track_count ?? stats.trackCount),
      depositCount: numberValue(stats.deposit_count ?? stats.depositCount),
      totalEdepMeV: numberValue(stats.total_edep_MeV ?? stats.totalEdepMeV),
    },
    particleCounts: asArray(row.particle_counts ?? row.particleCounts)
      .map(normalizeParticleCount)
      .filter((count): count is VisualizationParticleCount => Boolean(count)),
    energyPoints: asArray(row.energy_points ?? row.energyPoints)
      .map(normalizeEnergyPoint)
      .filter((point): point is VisualizationEnergyPoint => Boolean(point)),
    slicePlanes,
  }
}

function normalizeSourceRay(value: unknown): VisualizationSourceRay | null {
  const row = asRecord(value)
  const sourceId = text(row.source_id ?? row.sourceId ?? row.id)
  const start = vector(row.start_mm ?? row.start)
  const end = vector(row.end_mm ?? row.end)
  if (!sourceId || start.every((item, index) => item === end[index])) {
    return null
  }
  return {
    sourceId,
    particle: text(row.particle, 'particle'),
    energy: asRecord(row.energy),
    sourceShape: sourceShapeValue(row.source_shape ?? row.sourceShape),
    directionMode: directionModeValue(row.direction_mode ?? row.directionMode),
    sampleIndex: numberValue(row.sample_index ?? row.sampleIndex),
    sampleCount: Math.max(1, numberValue(row.sample_count ?? row.sampleCount, 1)),
    start,
    end,
  }
}

function sourceShapeValue(value: unknown): VisualizationSourceRay['sourceShape'] {
  const normalized = text(value, 'point').toLowerCase()
  return normalized === 'circle' || normalized === 'rectangle' ? normalized : 'point'
}

function directionModeValue(value: unknown): VisualizationSourceRay['directionMode'] {
  const normalized = text(value, 'mono').toLowerCase()
  if (normalized === 'isotropic' || normalized === 'cosine' || normalized === 'random') {
    return 'random'
  }
  return normalized === 'gaussian' || normalized === 'custom' ? normalized : 'mono'
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
  const sourceRays = asArray(row.source_rays ?? row.sourceRays)
    .map(normalizeSourceRay)
    .filter((sourceRay): sourceRay is VisualizationSourceRay => Boolean(sourceRay))

  return {
    status: normalizeStatus(row.status),
    visualEvents: numberValue(source.visual_events ?? row.visualEvents, 100),
    components,
    sourceRays,
    tracks,
    deposits,
    analysis: normalizeAnalysis(row.analysis),
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
