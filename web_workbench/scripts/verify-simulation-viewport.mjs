import { spawn } from 'node:child_process'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const workbenchRoot = path.resolve(__dirname, '..')
const outputDir = path.join(workbenchRoot, 'test-results')
const host = '127.0.0.1'
const port = Number(process.env.RADAGENT_VIEWPORT_VERIFY_PORT || 4197)
const baseUrl = `http://${host}:${port}`

function sampleVisualizationPayload() {
  const tracks = Array.from({ length: 100 }, (_, index) => {
    const offset = (index % 10 - 4.5) * 0.18
    const depthOffset = (Math.floor(index / 10) - 4.5) * 0.16
    return {
      event_id: index,
      track_id: index + 1,
      particle: index % 3 === 0 ? 'gamma' : 'proton',
      energy_MeV: 65 + index,
      points_mm: [
        [-3.8 + offset, 2.4, -6.2 + depthOffset],
        [-1.2 + offset, 0.8, -2.0 + depthOffset],
        [0.15 + offset * 0.2, 0.02, 0.0],
        [1.8 + offset, -0.7, 2.4 + depthOffset],
        [4.2 + offset, -2.0, 6.0 + depthOffset],
      ],
    }
  })

  const deposits = Array.from({ length: 36 }, (_, index) => {
    const x = ((index % 6) - 2.5) * 0.28
    const z = (Math.floor(index / 6) - 2.5) * 0.28
    return {
      event_id: index,
      track_id: index + 1,
      volume: 'silicon_detector',
      position_mm: [x, 0.08, z],
      edep_MeV: 0.18 + index * 0.01,
    }
  })

  return {
    status: 'ready',
    job_id: 'viewport-verification',
    source: {
      output_dir: '/tmp/radagent/viewport-verification',
      visual_events: 100,
      artifacts: {
        geometry_view: 'geometry_view.json',
        particle_tracks: 'particle_tracks.json',
        energy_deposits: 'energy_deposits.json',
      },
    },
    geometry: {
      units: { length: 'mm' },
      components: [
        {
          id: 'world',
          name: 'World',
          shape: 'box',
          material: 'G4_AIR',
          role: 'world',
          size_mm: [14, 10, 18],
          position_mm: [0, 0, 0],
          rotation_deg: [0, 0, 0],
          opacity: 0.08,
        },
        {
          id: 'silicon_detector',
          name: 'Silicon Detector',
          shape: 'box',
          material: 'G4_Si',
          role: 'detector sensitive',
          size_mm: [5.5, 0.28, 5.5],
          position_mm: [0, 0, 0],
          rotation_deg: [0, 0, 0],
          opacity: 0.52,
        },
        {
          id: 'aluminum_shield',
          name: 'Aluminum Shield',
          shape: 'box',
          material: 'G4_Al',
          role: 'shield',
          size_mm: [7.0, 0.55, 7.0],
          position_mm: [0, 1.4, 0],
          rotation_deg: [0, 0, 0],
          opacity: 0.38,
        },
      ],
    },
    tracks,
    deposits,
    stats: {
      components: 3,
      tracks: tracks.length,
      track_points: tracks.reduce((total, track) => total + track.points_mm.length, 0),
      deposits: deposits.length,
    },
    warnings: [],
  }
}

const status = {
  job_id: 'viewport-verification',
  user_query: '验证 3D Geant4 工作台视口',
  status: 'completed',
  current_phase: 'report',
  current_phase_idx: 6,
  completed_phases: ['prepare_workspace', 'context', 'g4_modeling', 'g4_codegen', 'validation', 'report'],
  execution_mode: 'web',
  run_mode: 'strict',
  workspace_root: '/tmp/radagent',
  job_workspace: '/tmp/radagent/viewport-verification',
  needs_confirmation: false,
  key_statuses: {},
  state: {},
}

const apiFixtures = {
  '/api/home': {
    home: {
      metrics: {
        projects: 1,
        jobs: 1,
        completed_jobs: 1,
        active_jobs: 0,
        artifacts: 3,
      },
      workflow_capabilities: [],
      projects: [],
      showcase_examples: [],
    },
  },
  '/api/commands': {
    commands: [
      {
        name: 'run',
        description: 'Run Geant4 workflow',
        tip: 'Run a simulation',
        module: 'workflow',
        connection: 'service',
        visible: true,
      },
    ],
  },
  '/api/status': { status },
  '/api/events': { events: [] },
  '/api/artifacts': { artifacts: [] },
  '/api/visualization': { visualization: sampleVisualizationPayload() },
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function waitForServer(serverUrl, timeoutMs = 20_000) {
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(serverUrl)
      if (response.ok) {
        return
      }
    } catch {
      // Retry until Vite has bound the port.
    }
    await wait(250)
  }
  throw new Error(`Vite server did not become ready at ${serverUrl}`)
}

function startVite() {
  const viteBin = path.join(workbenchRoot, 'node_modules', 'vite', 'bin', 'vite.js')
  const child = spawn(
    process.execPath,
    [viteBin, '--host', host, '--port', String(port), '--strictPort'],
    {
      cwd: workbenchRoot,
      env: { ...process.env, BROWSER: 'none' },
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  )
  child.stdout.on('data', (chunk) => process.stdout.write(chunk))
  child.stderr.on('data', (chunk) => process.stderr.write(chunk))
  return child
}

async function installApiFixtures(page) {
  await page.route('**/api/**', async (route) => {
    const requestUrl = new URL(route.request().url())
    const payload = apiFixtures[requestUrl.pathname]
    if (!payload) {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ ok: false, error: `Unhandled fixture route ${requestUrl.pathname}` }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(payload),
    })
  })
}

async function openWorkbench(page) {
  await installApiFixtures(page)
  await page.goto(baseUrl, { waitUntil: 'networkidle' })
  const intro = page.locator('button[aria-label="进入 RadAgent 首页"]')
  if (await intro.count()) {
    await intro.click({ force: true })
  }
  await page.getByRole('button', { name: /打开工作台/ }).click({ force: true })
  await page.locator('.simulation-viewport-stage canvas').waitFor({ state: 'visible', timeout: 15_000 })
}

async function readCanvasStats(page) {
  return page.evaluate(() => {
    const canvas = document.querySelector('.simulation-viewport-stage canvas')
    if (!(canvas instanceof HTMLCanvasElement)) {
      throw new Error('Simulation canvas was not mounted')
    }
    const gl = canvas.getContext('webgl2') || canvas.getContext('webgl')
    if (!gl) {
      throw new Error('Simulation canvas does not expose a WebGL context')
    }

    const width = gl.drawingBufferWidth
    const height = gl.drawingBufferHeight
    const pixels = new Uint8Array(width * height * 4)
    gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, pixels)

    let nonBlack = 0
    let red = 0
    let blue = 0
    let green = 0
    let hash = 2166136261
    const buckets = new Set()
    for (let index = 0; index < pixels.length; index += 4) {
      const r = pixels[index]
      const g = pixels[index + 1]
      const b = pixels[index + 2]
      const a = pixels[index + 3]
      if (a > 0 && (r > 8 || g > 8 || b > 8)) {
        nonBlack += 1
      }
      if (r > 180 && g < 110 && b < 110) {
        red += 1
      }
      if (b > 135 && r < 190) {
        blue += 1
      }
      if (g > 120 && r < 180 && b < 180) {
        green += 1
      }
      const bucket = `${r >> 4}:${g >> 4}:${b >> 4}:${a >> 7}`
      buckets.add(bucket)
      hash ^= (r << 16) + (g << 8) + b + a
      hash = Math.imul(hash, 16777619) >>> 0
    }

    return {
      width,
      height,
      nonBlack,
      red,
      blue,
      green,
      uniqueBuckets: buckets.size,
      hash,
    }
  })
}

function assertCanvasStats(label, stats) {
  if (stats.width < 260 || stats.height < 260) {
    throw new Error(`${label}: canvas too small ${stats.width}x${stats.height}`)
  }
  if (stats.nonBlack < stats.width * stats.height * 0.35) {
    throw new Error(`${label}: canvas appears blank (${stats.nonBlack} visible pixels)`)
  }
  if (stats.uniqueBuckets < 8) {
    throw new Error(`${label}: canvas lacks visual color variation (${stats.uniqueBuckets} buckets)`)
  }
  if (stats.red < 8) {
    throw new Error(`${label}: red energy deposit pixels were not detected`)
  }
  if (stats.blue < 8 && stats.green < 8) {
    throw new Error(`${label}: geometry or particle color pixels were not detected`)
  }
}

async function performOrbitInteraction(page, box, initialHash) {
  const gestures = [
    {
      from: [0.16, 0.62],
      to: [0.84, 0.28],
      wheel: -360,
    },
    {
      from: [0.22, 0.44],
      to: [0.78, 0.64],
      wheel: -420,
    },
    {
      from: [0.48, 0.72],
      to: [0.48, 0.24],
      wheel: 320,
    },
  ]
  let lastStats = null
  for (const gesture of gestures) {
    await page.mouse.move(
      box.x + box.width * gesture.from[0],
      box.y + box.height * gesture.from[1],
    )
    await page.mouse.down()
    await page.mouse.move(
      box.x + box.width * gesture.to[0],
      box.y + box.height * gesture.to[1],
      { steps: 14 },
    )
    await page.mouse.up()
    await page.mouse.wheel(0, gesture.wheel)
    await wait(650)
    lastStats = await readCanvasStats(page)
    if (lastStats.hash !== initialHash) {
      return lastStats
    }
  }
  return lastStats
}

async function verifyViewport(browser, viewport, label) {
  const page = await browser.newPage({ viewport })
  await openWorkbench(page)
  await wait(750)

  const viewportRoot = page.locator('.simulation-viewport')
  await viewportRoot.screenshot({ path: path.join(outputDir, `simulation-viewport-${label}.png`) })

  const initial = await readCanvasStats(page)
  assertCanvasStats(`${label} initial`, initial)

  const canvas = page.locator('.simulation-viewport-stage canvas')
  const box = await canvas.boundingBox()
  if (!box) {
    throw new Error(`${label}: simulation canvas has no layout box`)
  }
  const moved = await performOrbitInteraction(page, box, initial.hash)
  if (moved.hash === initial.hash) {
    throw new Error(
      `${label}: orbit/zoom interaction did not change canvas pixels; ` +
        `box=${JSON.stringify(box)} initial=${JSON.stringify(initial)} moved=${JSON.stringify(moved)}`,
    )
  }

  await page.getByRole('button', { name: /参考网格/ }).click()
  await wait(350)
  const noGrid = await readCanvasStats(page)
  assertCanvasStats(`${label} no-grid`, noGrid)

  await page.getByRole('button', { name: /显示轨迹/ }).click()
  await wait(350)
  const noParticles = await readCanvasStats(page)
  if (noParticles.red < 8) {
    throw new Error(`${label}: energy deposits disappeared when particle tracks were hidden`)
  }
  if (noParticles.hash === noGrid.hash) {
    throw new Error(`${label}: particle toggle did not change canvas pixels`)
  }

  await page.close()
  return { initial, moved, noGrid, noParticles }
}

async function main() {
  await mkdir(outputDir, { recursive: true })
  const server = startVite()
  let browser
  try {
    await waitForServer(baseUrl)
    browser = await chromium.launch({ headless: true })
    const desktop = await verifyViewport(browser, { width: 1280, height: 900 }, 'desktop')
    const mobile = await verifyViewport(browser, { width: 390, height: 844 }, 'mobile')
    console.log(
      JSON.stringify(
        {
          ok: true,
          screenshots: [
            path.relative(workbenchRoot, path.join(outputDir, 'simulation-viewport-desktop.png')),
            path.relative(workbenchRoot, path.join(outputDir, 'simulation-viewport-mobile.png')),
          ],
          desktop,
          mobile,
        },
        null,
        2,
      ),
    )
  } finally {
    if (browser) {
      await browser.close()
    }
    server.kill('SIGTERM')
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
