import { Eye, EyeOff, Grid, Info, RefreshCw } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import {
  VISIBLE_PARTICLE_TRACK_LIMIT,
  layerStats,
  type Vector3,
  type VisualizationComponent,
  type VisualizationPayload,
  type VisualizationSourceRay,
  type VisualizationTrack,
} from '../lib/visualizationPayload'

type SimulationViewportProps = {
  payload: VisualizationPayload | null
  loading?: boolean
  reviewFocus?: boolean
  onRefresh: () => void
}

type ViewportBounds = {
  min: Vector3
  max: Vector3
}

export type SourceStartMarker = {
  id: string
  kind: 'track' | 'point' | 'beam' | 'surface'
  label: string
  particle: string
  start: Vector3
  end: Vector3
}

export type ParticleColorLegendItem = {
  particle: string
  label: string
  color: string
}

const materialColors: Record<string, number> = {
  air: 0x8fb7d9,
  silicon: 0x61b596,
  si: 0x61b596,
  ge: 0x7c8bd9,
  germanium: 0x7c8bd9,
  aluminum: 0xc8cbd0,
  al: 0xc8cbd0,
  lead: 0x7a7480,
  pb: 0x7a7480,
  water: 0x6aaed6,
  polyethylene: 0xb4c872,
}

const emptyPayload: VisualizationPayload = {
  status: 'waiting',
  visualEvents: 100,
  components: [],
  sourceRays: [],
  tracks: [],
  deposits: [],
  warnings: [],
}

const commonParticleColors: Array<{ label: string; color: string; match: (particle: string) => boolean }> = [
  { label: '电子', color: '#2aa7ff', match: (particle) => particle === 'electron' || particle === 'e-' || particle === 'e+' || particle.includes('electron') },
  { label: '质子', color: '#ff8d3a', match: (particle) => particle.includes('proton') || particle === 'p' },
  { label: '中子', color: '#7c5cff', match: (particle) => particle.includes('neutron') },
  { label: '光子 / Gamma', color: '#f2cf3a', match: (particle) => particle.includes('gamma') || particle.includes('photon') },
]

const fallbackParticleColors = ['#00a88f', '#d45c9f', '#8f7a2d', '#4f8bd8', '#b65f2a', '#6f7a89', '#c24bd6']

function normalizeParticleName(particle: string): string {
  return particle.trim().toLowerCase() || 'unknown'
}

function commonParticleColor(particle: string): { label: string; color: string } | null {
  const normalized = normalizeParticleName(particle)
  const match = commonParticleColors.find((entry) => entry.match(normalized))
  return match ? { label: match.label, color: match.color } : null
}

export function particleColorForName(particle: string, fallbackIndex = 0): string {
  return commonParticleColor(particle)?.color ?? fallbackParticleColors[fallbackIndex % fallbackParticleColors.length]
}

export function particleColorLegendFor(payload: VisualizationPayload): ParticleColorLegendItem[] {
  const particles: string[] = []
  for (const sourceRay of payload.sourceRays) {
    if (sourceRay.particle && !particles.includes(sourceRay.particle)) {
      particles.push(sourceRay.particle)
    }
  }
  for (const track of payload.tracks) {
    if (track.particle && !particles.includes(track.particle)) {
      particles.push(track.particle)
    }
  }

  let otherIndex = 0
  return particles.map((particle) => {
    const common = commonParticleColor(particle)
    if (common) {
      return { particle, label: common.label, color: common.color }
    }
    otherIndex += 1
    return {
      particle,
      label: `其他粒子${otherIndex}`,
      color: fallbackParticleColors[(otherIndex - 1) % fallbackParticleColors.length],
    }
  })
}

export function shouldShowSourcePreview(payload: VisualizationPayload): boolean {
  return payload.sourceRays.length > 0 && payload.tracks.length === 0
}

export function sourceStartMarkersForViewport(
  payload: VisualizationPayload,
  showParticles: boolean,
  limit = 10,
): SourceStartMarker[] {
  if (!showParticles) {
    return []
  }
  if (payload.tracks.length > 0) {
    return orderedParticleTracks(payload, true, VISIBLE_PARTICLE_TRACK_LIMIT)
      .filter((track) => track.points.length >= 2)
      .slice(0, limit)
      .map((track, index) => ({
        id: `track:${track.eventId}:${track.trackId}`,
        kind: 'track',
        label: `source-start-${index + 1}`,
        particle: track.particle,
        start: track.points[0],
        end: track.points[1],
      }))
  }
  return payload.sourceRays.slice(0, limit).map((ray, index) => ({
    id: `source:${ray.sourceId}:${ray.sampleIndex}`,
    kind: ray.sourceShape === 'rectangle' || ray.sourceShape === 'circle'
      ? 'surface'
      : ray.directionMode === 'random'
        ? 'point'
        : 'beam',
    label: `source-start-${index + 1}`,
    particle: ray.particle,
    start: ray.start,
    end: ray.end,
  }))
}

function particleColorLookup(payload: VisualizationPayload): Map<string, string> {
  return new Map(particleColorLegendFor(payload).map((item) => [item.particle, item.color]))
}

function colorHexToNumber(color: string): number {
  return Number.parseInt(color.replace('#', ''), 16)
}

function colorFor(component: VisualizationComponent): number {
  const text = `${component.material} ${component.role} ${component.id}`.toLowerCase()
  if (component.color && /^#[0-9a-f]{6}$/i.test(component.color)) {
    return Number.parseInt(component.color.slice(1), 16)
  }
  for (const [keyword, color] of Object.entries(materialColors)) {
    if (text.includes(keyword)) {
      return color
    }
  }
  if (text.includes('world')) {
    return 0x9aa5ad
  }
  if (text.includes('shield')) {
    return 0xb7aa65
  }
  if (text.includes('detector') || text.includes('sensitive')) {
    return 0x55b884
  }
  return 0x79a7c9
}

function toVector3(point: Vector3): THREE.Vector3 {
  return new THREE.Vector3(point[0], point[1], point[2])
}

function componentText(component: VisualizationComponent): string {
  return `${component.id} ${component.name} ${component.material} ${component.role ?? ''}`.toLowerCase()
}

export function isWorldComponent(component: VisualizationComponent): boolean {
  const text = componentText(component)
  return text.includes('world') || component.role?.toLowerCase().includes('world') === true
}

function isShellComponent(component: VisualizationComponent): boolean {
  const text = componentText(component)
  return (
    isWorldComponent(component) ||
    text.includes('shield') ||
    text.includes('veto') ||
    text.includes('container') ||
    text.includes('housing') ||
    text.includes('dead_layer') ||
    text.includes('dead layer')
  )
}

export function focusComponentsForViewport(payload: VisualizationPayload): VisualizationComponent[] {
  const focusComponents = payload.components.filter((component) => !isWorldComponent(component))
  return focusComponents.length > 0 ? focusComponents : payload.components
}

export function depositPointSizeForExtent(extent: number): number {
  return Math.max(0.75, Math.min(1.8, extent * 0.006))
}

function trackPathLength(track: VisualizationTrack): number {
  return track.points.reduce((total, point, index) => {
    if (index === 0) {
      return total
    }
    const previous = track.points[index - 1]
    return total + Math.hypot(point[0] - previous[0], point[1] - previous[1], point[2] - previous[2])
  }, 0)
}

function isPrimaryLikeParticle(particle: string): boolean {
  const normalized = particle.toLowerCase()
  return (
    normalized.includes('gamma') ||
    normalized.includes('photon') ||
    normalized.includes('proton') ||
    normalized.includes('ion') ||
    normalized.includes('neutron')
  )
}

function trackPriority(track: VisualizationTrack): number {
  const particle = track.particle.toLowerCase()
  const incomingBonus = particle.includes('gamma') || particle.includes('photon') || particle.includes('neutron') ? 2200 : 0
  const chargedPrimaryBonus = particle.includes('proton') || particle.includes('ion') ? 900 : 0
  return incomingBonus + chargedPrimaryBonus + trackPathLength(track) * 12 + track.energyMeV * 35 + track.points.length
}

export function orderedParticleTracks(
  payload: VisualizationPayload,
  showParticles: boolean,
  limit = VISIBLE_PARTICLE_TRACK_LIMIT,
): VisualizationTrack[] {
  if (!showParticles) {
    return []
  }
  return [...payload.tracks]
    .sort((left, right) => {
      const scoreDelta = trackPriority(right) - trackPriority(left)
      if (scoreDelta !== 0) {
        return scoreDelta
      }
      return left.eventId - right.eventId || left.trackId - right.trackId
    })
    .slice(0, limit)
}

export function highlightedParticleTracks(
  payload: VisualizationPayload,
  showParticles: boolean,
  limit = 12,
): VisualizationTrack[] {
  if (!showParticles) {
    return []
  }
  return orderedParticleTracks(payload, true, VISIBLE_PARTICLE_TRACK_LIMIT)
    .filter((track) => isPrimaryLikeParticle(track.particle))
    .slice(0, limit)
}

function rounded(value: number): string {
  return Number.isFinite(value) ? value.toFixed(3) : '0.000'
}

function vectorSignature(point: Vector3): string {
  return `${rounded(point[0])},${rounded(point[1])},${rounded(point[2])}`
}

function hashText(value: string): string {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(36)
}

export function visualizationSceneSignature(payload: VisualizationPayload): string {
  const parts: string[] = [payload.status, String(payload.visualEvents)]
  for (const component of payload.components) {
    parts.push(
      [
        'c',
        component.id,
        component.shape,
        component.material,
        component.role ?? '',
        vectorSignature(component.size),
        vectorSignature(component.position),
        vectorSignature(component.rotation),
        rounded(component.opacity),
      ].join(':'),
    )
  }
  for (const sourceRay of payload.sourceRays ?? []) {
    parts.push(
      [
        's',
        sourceRay.sourceId,
        sourceRay.particle,
        vectorSignature(sourceRay.start),
        vectorSignature(sourceRay.end),
      ].join(':'),
    )
  }
  for (const track of payload.tracks) {
    parts.push(
      [
        't',
        track.eventId,
        track.trackId,
        track.particle,
        rounded(track.energyMeV),
        track.points.map(vectorSignature).join('|'),
      ].join(':'),
    )
  }
  for (const deposit of payload.deposits) {
    parts.push(
      [
        'd',
        deposit.eventId,
        deposit.trackId,
        deposit.volume,
        vectorSignature(deposit.position),
        rounded(deposit.edepMeV),
      ].join(':'),
    )
  }
  return `${payload.components.length}:${payload.tracks.length}:${payload.deposits.length}:${hashText(parts.join('\n'))}`
}

function componentOpacity(component: VisualizationComponent): number {
  if (isWorldComponent(component)) {
    return 0.035
  }
  if (isShellComponent(component)) {
    return Math.min(component.opacity, 0.24)
  }
  return Math.min(component.opacity, 0.56)
}

function componentMesh(component: VisualizationComponent, focusExtent: number): THREE.Object3D {
  const lowerShape = component.shape.toLowerCase()
  const isWorld = isWorldComponent(component)
  const material = new THREE.MeshStandardMaterial({
    color: colorFor(component),
    transparent: true,
    opacity: componentOpacity(component),
    roughness: 0.52,
    metalness: 0.08,
    depthWrite: false,
    side: THREE.DoubleSide,
    wireframe: isWorld || component.role?.toLowerCase().includes('container'),
  })

  let geometry: THREE.BufferGeometry
  if (lowerShape.includes('sphere')) {
    geometry = new THREE.SphereGeometry(Math.max(component.size[0], component.size[1], component.size[2]) / 2, 32, 18)
  } else if (lowerShape.includes('tube') || lowerShape.includes('cylinder')) {
    const radius = Math.max(
      Math.max(component.size[0], component.size[1]) / 2,
      isWorld ? 0 : Math.min(3.5, Math.max(0.75, focusExtent * 0.01)),
    )
    geometry = new THREE.CylinderGeometry(radius, radius, Math.max(component.size[2], 0.1), 36)
    geometry.rotateX(Math.PI / 2)
  } else {
    geometry = new THREE.BoxGeometry(
      Math.max(component.size[0], 0.1),
      Math.max(component.size[1], 0.1),
      Math.max(component.size[2], 0.1),
    )
  }

  const group = new THREE.Group()
  group.position.set(...component.position)
  group.rotation.set(
    THREE.MathUtils.degToRad(component.rotation[0]),
    THREE.MathUtils.degToRad(component.rotation[1]),
    THREE.MathUtils.degToRad(component.rotation[2]),
  )

  const mesh = new THREE.Mesh(geometry, material)
  group.add(mesh)

  if (!isWorld) {
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(geometry, 12),
      new THREE.LineBasicMaterial({
        color: colorFor(component),
        transparent: true,
        opacity: 0.86,
        depthTest: false,
      }),
    )
    group.add(edges)
  }

  return group
}

function modelBoundsFor(payload: VisualizationPayload): THREE.Box3 {
  const box = new THREE.Box3()
  for (const component of focusComponentsForViewport(payload)) {
    const half = new THREE.Vector3(component.size[0] / 2, component.size[1] / 2, component.size[2] / 2)
    const center = toVector3(component.position)
    box.expandByPoint(center.clone().sub(half))
    box.expandByPoint(center.clone().add(half))
  }
  return box
}

function boundsFor(payload: VisualizationPayload): THREE.Box3 {
  const box = modelBoundsFor(payload)
  for (const track of payload.tracks) {
    if (isPrimaryLikeParticle(track.particle)) {
      for (const point of track.points) {
        box.expandByPoint(toVector3(point))
      }
    }
  }
  if (box.isEmpty()) {
    for (const track of payload.tracks) {
      for (const point of track.points) {
        box.expandByPoint(toVector3(point))
      }
    }
  }
  for (const sourceRay of payload.sourceRays ?? []) {
    box.expandByPoint(toVector3(sourceRay.start))
    box.expandByPoint(toVector3(sourceRay.end))
  }
  for (const deposit of payload.deposits) {
    box.expandByPoint(toVector3(deposit.position))
  }
  if (box.isEmpty()) {
    box.expandByPoint(new THREE.Vector3(-5, -5, -5))
    box.expandByPoint(new THREE.Vector3(5, 5, 5))
  }
  return box
}

function pointInsideBounds(point: Vector3, bounds: ViewportBounds): boolean {
  return (
    point[0] >= bounds.min[0] &&
    point[0] <= bounds.max[0] &&
    point[1] >= bounds.min[1] &&
    point[1] <= bounds.max[1] &&
    point[2] >= bounds.min[2] &&
    point[2] <= bounds.max[2]
  )
}

export function trackPointsForViewport(track: VisualizationTrack, bounds: ViewportBounds): Vector3[] {
  if (isPrimaryLikeParticle(track.particle)) {
    return track.points
  }
  const visiblePoints = track.points.filter((point) => pointInsideBounds(point, bounds))
  return visiblePoints.length >= 2 ? visiblePoints : []
}

function compactTrackPoints(track: VisualizationTrack, viewportBounds: ViewportBounds): THREE.Vector3[] {
  const points: THREE.Vector3[] = []
  for (const point of trackPointsForViewport(track, viewportBounds)) {
    const vector = toVector3(point)
    const previous = points[points.length - 1]
    if (!previous || previous.distanceToSquared(vector) > 1e-8) {
      points.push(vector)
    }
  }
  return points
}

function colorForTrack(track: VisualizationTrack, colors: Map<string, string>): number {
  return colorHexToNumber(colors.get(track.particle) ?? particleColorForName(track.particle))
}

export function trackTubeRadiusForExtent(track: VisualizationTrack, extent: number): number {
  const normalized = track.particle.toLowerCase()
  const base = Math.max(0.28, Math.min(0.82, extent * 0.003))
  if (normalized.includes('neutron')) {
    return base * 0.92
  }
  if (isPrimaryLikeParticle(track.particle)) {
    return base
  }
  return base * 0.72
}

function sourceRayColor(ray: VisualizationSourceRay, colors: Map<string, string>): number {
  return colorHexToNumber(colors.get(ray.particle) ?? particleColorForName(ray.particle))
}

function colorForMarker(marker: SourceStartMarker, colors: Map<string, string>): number {
  return colorHexToNumber(colors.get(marker.particle) ?? particleColorForName(marker.particle))
}

function addSourceRay(root: THREE.Group, ray: VisualizationSourceRay, extent: number, colors: Map<string, string>): void {
  const start = toVector3(ray.start)
  const end = toVector3(ray.end)
  const delta = end.clone().sub(start)
  const length = delta.length()
  if (length <= 1e-8) {
    return
  }
  const color = sourceRayColor(ray, colors)
  const radius = Math.max(0.45, Math.min(1.8, extent * 0.008))
  const curve = new THREE.LineCurve3(start, end)
  root.add(
    new THREE.Mesh(
      new THREE.TubeGeometry(curve, 16, radius, 8, false),
      new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.88,
        depthTest: false,
      }),
    ),
  )
  root.add(
    new THREE.ArrowHelper(
      delta.normalize(),
      start,
      length,
      color,
      Math.max(5, Math.min(14, extent * 0.07)),
      Math.max(2, Math.min(7, extent * 0.035)),
    ),
  )
}

function addSourceStartMarker(
  root: THREE.Group,
  marker: SourceStartMarker,
  extent: number,
  colors: Map<string, string>,
): void {
  const start = toVector3(marker.start)
  const end = toVector3(marker.end)
  const delta = end.clone().sub(start)
  const length = delta.length()
  if (length <= 1e-8) {
    return
  }
  const color = colorForMarker(marker, colors)
  const group = new THREE.Group()
  group.name = marker.label
  group.position.copy(start)
  const sphereRadius = Math.max(0.9, Math.min(3.2, extent * 0.014))
  const markerMaterial = new THREE.MeshStandardMaterial({
    color,
    emissive: color,
    emissiveIntensity: 0.36,
    roughness: 0.36,
    metalness: 0.08,
    depthTest: false,
  })
  group.add(new THREE.Mesh(new THREE.SphereGeometry(sphereRadius, 20, 12), markerMaterial))

  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(sphereRadius * 1.8, Math.max(0.08, sphereRadius * 0.12), 8, 36),
    new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: marker.kind === 'surface' ? 0.7 : 0.54,
      depthTest: false,
    }),
  )
  ring.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), delta.clone().normalize())
  group.add(ring)
  root.add(group)

  const arrowLength = Math.max(Math.min(length, extent * 0.22), extent * 0.08)
  root.add(
    new THREE.ArrowHelper(
      delta.normalize(),
      start,
      arrowLength,
      color,
      Math.max(4, Math.min(12, extent * 0.055)),
      Math.max(1.8, Math.min(6, extent * 0.028)),
    ),
  )
}

function addParticleTrack(
  root: THREE.Group,
  track: VisualizationTrack,
  index: number,
  extent: number,
  viewportBounds: ViewportBounds,
  colors: Map<string, string>,
): void {
  const points = compactTrackPoints(track, viewportBounds)
  if (points.length < 2) {
    return
  }
  const color = colorForTrack(track, colors)
  const geometry = new THREE.BufferGeometry().setFromPoints(points)
  const isHighlighted = isPrimaryLikeParticle(track.particle)
  const opacity = isHighlighted ? 0.54 : 0.42
  root.add(
    new THREE.Line(
      geometry,
      new THREE.LineBasicMaterial({
        color,
        transparent: true,
        opacity,
        depthTest: true,
      }),
    ),
  )

  if (index < 72) {
    const tubeRadius = trackTubeRadiusForExtent(track, extent)
    const curve = new THREE.CatmullRomCurve3(points)
    root.add(
      new THREE.Mesh(
        new THREE.TubeGeometry(curve, Math.max(points.length * 4, 8), tubeRadius, 6, false),
        new THREE.MeshBasicMaterial({
          color,
          transparent: true,
          opacity: isHighlighted ? 0.5 : 0.36,
          depthTest: false,
        }),
      ),
    )
  }
}

function disposeObjectTree(object: THREE.Object3D): void {
  object.traverse((node) => {
    const resource = node as THREE.Object3D & {
      geometry?: THREE.BufferGeometry
      material?: (THREE.Material & { map?: THREE.Texture }) | Array<THREE.Material & { map?: THREE.Texture }>
    }
    resource.geometry?.dispose()
    const material = resource.material
    if (Array.isArray(material)) {
      material.forEach((item) => {
        item.map?.dispose()
        item.dispose()
      })
    } else {
      material?.map?.dispose()
      material?.dispose()
    }
  })
}

export default function SimulationViewport({
  payload,
  loading = false,
  reviewFocus = false,
  onRefresh,
}: SimulationViewportProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const cameraStateRef = useRef<{
    position: THREE.Vector3
    target: THREE.Vector3
  } | null>(null)
  const previousSceneSignatureRef = useRef<string | null>(null)
  const [showParticles, setShowParticles] = useState(true)
  const [showReferenceGrid, setShowReferenceGrid] = useState(true)
  const data = payload ?? emptyPayload
  const stats = useMemo(() => layerStats(data, showParticles), [data, showParticles])
  const sceneSignature = useMemo(() => visualizationSceneSignature(data), [data])
  const particleLegend = useMemo(() => particleColorLegendFor(data), [sceneSignature])

  useEffect(() => {
    const container = containerRef.current
    if (!container) {
      return undefined
    }

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0xf8f4ed)
    const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 100000)
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      preserveDrawingBuffer: true,
    })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    container.appendChild(renderer.domElement)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.zoomSpeed = 0.75

    scene.add(new THREE.HemisphereLight(0xffffff, 0xe5d8c8, 2.1))
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.35)
    keyLight.position.set(20, 30, 30)
    scene.add(keyLight)

    const root = new THREE.Group()
    scene.add(root)
    root.add(new THREE.AxesHelper(8))
    const hasSceneData = data.components.length > 0 || data.sourceRays.length > 0 || data.tracks.length > 0 || data.deposits.length > 0

    const bounds = boundsFor(data)
    const center = new THREE.Vector3()
    const size = new THREE.Vector3()
    bounds.getCenter(center)
    bounds.getSize(size)
    const extent = Math.max(size.x, size.y, size.z, 12)
    const modelBounds = modelBoundsFor(data)
    const clipBounds = modelBounds.isEmpty() ? bounds : modelBounds
    const viewportBounds: ViewportBounds = {
      min: [clipBounds.min.x, clipBounds.min.y, clipBounds.min.z],
      max: [clipBounds.max.x, clipBounds.max.y, clipBounds.max.z],
    }

    for (const component of data.components) {
      root.add(componentMesh(component, extent))
    }

    const visibleTracks = orderedParticleTracks(data, showParticles)
    const sourceMarkers = sourceStartMarkersForViewport(data, showParticles)
    const colors = particleColorLookup(data)
    if (showParticles) {
      if (shouldShowSourcePreview(data)) {
        for (const sourceRay of data.sourceRays) {
          addSourceRay(root, sourceRay, extent, colors)
        }
      }
      for (const marker of sourceMarkers) {
        addSourceStartMarker(root, marker, extent, colors)
      }
      for (const [index, track] of visibleTracks.entries()) {
        addParticleTrack(root, track, index, extent, viewportBounds, colors)
      }
    }

    if (data.deposits.length > 0) {
      const positions = new Float32Array(data.deposits.length * 3)
      data.deposits.forEach((deposit, index) => {
        positions[index * 3] = deposit.position[0]
        positions[index * 3 + 1] = deposit.position[1]
        positions[index * 3 + 2] = deposit.position[2]
      })
      const geometry = new THREE.BufferGeometry()
      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
      const material = new THREE.PointsMaterial({
        color: 0xff3b30,
        size: depositPointSizeForExtent(extent),
        sizeAttenuation: true,
        depthTest: true,
        transparent: true,
        opacity: 0.78,
      })
      root.add(new THREE.Points(geometry, material))
    }

    if (showReferenceGrid) {
      const grid = new THREE.GridHelper(extent * 1.9, 24, 0xb94138, 0x8f867b)
      const gridMaterials = Array.isArray(grid.material) ? grid.material : [grid.material]
      gridMaterials.forEach((material) => {
        material.transparent = true
        material.opacity = hasSceneData ? 0.2 : 0.44
      })
      grid.position.y = hasSceneData ? Math.min(bounds.min.y, 0) - extent * 0.03 : 0
      root.add(grid)
    }

    if (!hasSceneData) {
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(extent * 0.34, Math.max(extent * 0.008, 0.03), 12, 96),
        new THREE.MeshBasicMaterial({ color: 0xb94138, transparent: true, opacity: 0.66 }),
      )
      ring.rotation.x = Math.PI / 2
      ring.position.y = extent * 0.02
      root.add(ring)

      const marker = new THREE.Mesh(
        new THREE.SphereGeometry(extent * 0.035, 24, 12),
        new THREE.MeshStandardMaterial({
          color: 0x23785a,
          emissive: 0x123d2d,
          emissiveIntensity: 0.22,
          roughness: 0.48,
        }),
      )
      marker.position.set(0, extent * 0.08, 0)
      root.add(marker)
    }

    const canReuseCamera = previousSceneSignatureRef.current === sceneSignature && cameraStateRef.current
    if (canReuseCamera && cameraStateRef.current) {
      camera.position.copy(cameraStateRef.current.position)
      controls.target.copy(cameraStateRef.current.target)
    } else {
      controls.target.copy(center)
      camera.position.set(center.x + extent * 1.35, center.y + extent * 0.9, center.z + extent * 1.55)
    }
    camera.near = Math.max(extent / 10000, 0.01)
    camera.far = extent * 100
    camera.updateProjectionMatrix()
    controls.update()

    const saveCameraState = () => {
      cameraStateRef.current = {
        position: camera.position.clone(),
        target: controls.target.clone(),
      }
    }
    controls.addEventListener('change', saveCameraState)
    previousSceneSignatureRef.current = sceneSignature

    let frame = 0
    const resize = () => {
      const box = container.getBoundingClientRect()
      const width = Math.max(260, box.width)
      const height = Math.max(260, box.height)
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
    }
    const observer = new ResizeObserver(resize)
    observer.observe(container)
    resize()

    const render = () => {
      controls.update()
      renderer.render(scene, camera)
      frame = window.requestAnimationFrame(render)
    }
    frame = window.requestAnimationFrame(render)

    return () => {
      saveCameraState()
      window.cancelAnimationFrame(frame)
      observer.disconnect()
      controls.removeEventListener('change', saveCameraState)
      controls.dispose()
      renderer.dispose()
      disposeObjectTree(root)
      container.removeChild(renderer.domElement)
    }
  }, [sceneSignature, showParticles, showReferenceGrid])

  return (
    <section className={`simulation-viewport${reviewFocus ? ' review-focus' : ''}`} aria-label="Geant4 3D visualization">
      <div className="simulation-viewport-stage" ref={containerRef} />
      {reviewFocus ? (
        <div className="simulation-review-focus-badge" aria-live="polite">
          <strong>模型核对</strong>
          <span>请对照参数清单检查几何、材料和粒子源是否符合预期</span>
        </div>
      ) : null}
      <div className="simulation-viewport-toolbar">
        <div>
          <strong>3D 模型视图</strong>
          <span>{data.status === 'ready' ? '100 粒子可视化数据已就绪' : '等待可视化产物 · 参考网格'}</span>
        </div>
        <div className="particle-legend-tooltip">
          <button type="button" aria-label="查看粒子颜色图例" title="粒子颜色图例">
            <Info size={15} />
          </button>
          <div className="particle-legend-popover" role="tooltip">
            {particleLegend.length > 0 ? (
              particleLegend.map((item) => (
                <span key={`${item.label}-${item.particle}`}>
                  <i style={{ backgroundColor: item.color }} />
                  <strong>{item.label}</strong>
                  <em>{item.particle}</em>
                </span>
              ))
            ) : (
              <span>
                <i style={{ backgroundColor: particleColorForName('gamma') }} />
                <strong>暂无轨迹</strong>
                <em>等待真实粒子数据</em>
              </span>
            )}
          </div>
        </div>
        <button
          type="button"
          title="切换粒子轨迹显示 Toggle particle tracks"
          aria-pressed={showParticles}
          onClick={() => setShowParticles((current) => !current)}
        >
          {showParticles ? <Eye size={16} /> : <EyeOff size={16} />}
          <span>{showParticles ? '显示轨迹' : '隐藏轨迹'}</span>
        </button>
        <button
          type="button"
          title="切换参考网格 Toggle reference grid"
          aria-pressed={showReferenceGrid}
          onClick={() => setShowReferenceGrid((current) => !current)}
        >
          <Grid size={16} />
          <span>参考网格</span>
        </button>
        <button type="button" title="刷新 3D 数据 Refresh 3D data" onClick={onRefresh} disabled={loading}>
          <RefreshCw size={16} />
          <span>{loading ? '加载中' : '刷新数据'}</span>
        </button>
      </div>
      <div className="simulation-viewport-stats" aria-label="Visualization layer stats">
        <span>几何 {stats.components}</span>
        <span>轨迹 {stats.tracks}</span>
        <span>能量沉积 {stats.deposits}</span>
        <span>仿真事件 {data.visualEvents}</span>
      </div>
      {data.status !== 'ready' ? (
        <div className="simulation-viewport-empty">
          <strong>等待 100 粒子可视化输出</strong>
          <span>{data.warnings[0] || '运行模拟后生成几何、轨迹和能量沉积分布。'}</span>
        </div>
      ) : null}
    </section>
  )
}
