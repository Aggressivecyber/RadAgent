import { Eye, EyeOff, Grid, RefreshCw } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import {
  layerStats,
  visibleParticleTracks,
  type Vector3,
  type VisualizationComponent,
  type VisualizationPayload,
} from '../lib/visualizationPayload'

type SimulationViewportProps = {
  payload: VisualizationPayload | null
  loading?: boolean
  onRefresh: () => void
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
  tracks: [],
  deposits: [],
  warnings: [],
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

function componentMesh(component: VisualizationComponent): THREE.Object3D {
  const lowerShape = component.shape.toLowerCase()
  const isWorld = component.id.toLowerCase() === 'world' || component.role?.toLowerCase().includes('world')
  const opacity = isWorld ? 0.08 : component.opacity
  const material = new THREE.MeshStandardMaterial({
    color: colorFor(component),
    transparent: true,
    opacity,
    roughness: 0.52,
    metalness: 0.08,
    wireframe: isWorld || component.role?.toLowerCase().includes('container'),
  })

  let geometry: THREE.BufferGeometry
  if (lowerShape.includes('sphere')) {
    geometry = new THREE.SphereGeometry(Math.max(component.size[0], component.size[1], component.size[2]) / 2, 32, 18)
  } else if (lowerShape.includes('tube') || lowerShape.includes('cylinder')) {
    const radius = Math.max(component.size[0], component.size[1]) / 2
    geometry = new THREE.CylinderGeometry(radius, radius, Math.max(component.size[2], 0.1), 36)
    geometry.rotateX(Math.PI / 2)
  } else {
    geometry = new THREE.BoxGeometry(
      Math.max(component.size[0], 0.1),
      Math.max(component.size[1], 0.1),
      Math.max(component.size[2], 0.1),
    )
  }

  const mesh = new THREE.Mesh(geometry, material)
  mesh.position.set(...component.position)
  mesh.rotation.set(
    THREE.MathUtils.degToRad(component.rotation[0]),
    THREE.MathUtils.degToRad(component.rotation[1]),
    THREE.MathUtils.degToRad(component.rotation[2]),
  )
  return mesh
}

function boundsFor(payload: VisualizationPayload): THREE.Box3 {
  const box = new THREE.Box3()
  for (const component of payload.components) {
    const half = new THREE.Vector3(component.size[0] / 2, component.size[1] / 2, component.size[2] / 2)
    const center = toVector3(component.position)
    box.expandByPoint(center.clone().sub(half))
    box.expandByPoint(center.clone().add(half))
  }
  for (const track of payload.tracks) {
    for (const point of track.points) {
      box.expandByPoint(toVector3(point))
    }
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

function disposeObjectTree(object: THREE.Object3D): void {
  object.traverse((node) => {
    const resource = node as THREE.Object3D & {
      geometry?: THREE.BufferGeometry
      material?: THREE.Material | THREE.Material[]
    }
    resource.geometry?.dispose()
    const material = resource.material
    if (Array.isArray(material)) {
      material.forEach((item) => item.dispose())
    } else {
      material?.dispose()
    }
  })
}

export default function SimulationViewport({
  payload,
  loading = false,
  onRefresh,
}: SimulationViewportProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [showParticles, setShowParticles] = useState(true)
  const [showReferenceGrid, setShowReferenceGrid] = useState(true)
  const data = payload ?? emptyPayload
  const stats = useMemo(() => layerStats(data, showParticles), [data, showParticles])

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
    const hasSceneData = data.components.length > 0 || data.tracks.length > 0 || data.deposits.length > 0

    for (const component of data.components) {
      root.add(componentMesh(component))
    }

    const visibleTracks = visibleParticleTracks(data, showParticles)
    if (showParticles) {
      for (const track of visibleTracks) {
        const points = track.points.map(toVector3)
        const geometry = new THREE.BufferGeometry().setFromPoints(points)
        const material = new THREE.LineBasicMaterial({
          color: track.particle.toLowerCase().includes('gamma') ? 0xe5cf4a : 0x9fd2ff,
          transparent: true,
          opacity: 0.78,
        })
        root.add(new THREE.Line(geometry, material))
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
        size: 7,
        sizeAttenuation: false,
        depthTest: false,
      })
      root.add(new THREE.Points(geometry, material))
    }

    const bounds = boundsFor(data)
    const center = new THREE.Vector3()
    const size = new THREE.Vector3()
    bounds.getCenter(center)
    bounds.getSize(size)
    const extent = Math.max(size.x, size.y, size.z, 12)
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

    controls.target.copy(center)
    camera.position.set(center.x + extent * 1.35, center.y + extent * 0.9, center.z + extent * 1.55)
    camera.near = Math.max(extent / 10000, 0.01)
    camera.far = extent * 100
    camera.updateProjectionMatrix()

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
      window.cancelAnimationFrame(frame)
      observer.disconnect()
      controls.dispose()
      renderer.dispose()
      disposeObjectTree(root)
      container.removeChild(renderer.domElement)
    }
  }, [data, showParticles, showReferenceGrid])

  return (
    <section className="simulation-viewport" aria-label="Geant4 3D visualization">
      <div className="simulation-viewport-stage" ref={containerRef} />
      <div className="simulation-viewport-toolbar">
        <div>
          <strong>3D 模型视图</strong>
          <span>{data.status === 'ready' ? '100 粒子可视化数据已就绪' : '等待可视化产物 · 参考网格'}</span>
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
