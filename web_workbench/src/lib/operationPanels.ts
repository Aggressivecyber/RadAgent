export type OperationMetric = {
  label: string
  value: string
}

export type OperationArtifact = {
  path: string
  kind: string
  stage: string
}

export type OperationPanel = {
  title: string
  summary: string
  metrics: OperationMetric[]
  preview: string
  artifacts: OperationArtifact[]
}

const operationViews = new Set([
  'build',
  'simulation',
  'workbench',
  'visual-review',
  'report',
  'demo',
  'mode',
  'history',
  'exit',
])

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function text(value: unknown, fallback = ''): string {
  const normalized = String(value ?? '').trim()
  return normalized || fallback
}

function passFail(value: unknown): string {
  return value === true ? 'passed' : 'failed'
}

function returnCodeStatus(value: unknown): string {
  const row = asRecord(value)
  if (!('returncode' in row)) {
    return 'not run'
  }
  return Number(row.returncode) === 0 ? 'ok' : 'failed'
}

function artifactRows(value: unknown): OperationArtifact[] {
  return asArray(value).map((item) => {
    const row = asRecord(item)
    return {
      path: text(row.path, 'unknown artifact'),
      kind: text(row.kind, 'artifact'),
      stage: text(row.stage),
    }
  })
}

export function isOperationPanelView(view: string): boolean {
  return operationViews.has(view)
}

export function createOperationPanel(view: string, data: unknown): OperationPanel | null {
  const row = asRecord(data)

  if (view === 'build') {
    const executable = text(row.executable_path, 'not available')
    return {
      title: 'Build result',
      summary: text(row.errors, row.success === true ? 'Build completed.' : 'Build failed.'),
      metrics: [
        { label: 'Result', value: passFail(row.success) },
        { label: 'Configure', value: returnCodeStatus(row.configure) },
        { label: 'Build', value: returnCodeStatus(row.build) },
        { label: 'Executable', value: executable },
      ],
      preview: text(row.errors),
      artifacts: [],
    }
  }

  if (view === 'simulation') {
    return {
      title: 'Simulation result',
      summary: text(row.errors, row.success === true ? 'Simulation completed.' : 'Simulation failed.'),
      metrics: [
        { label: 'Result', value: passFail(row.success) },
        { label: 'Output', value: text(row.output_dir, 'not available') },
      ],
      preview: text(row.errors || row.log),
      artifacts: [],
    }
  }

  if (view === 'workbench') {
    const executable = text(row.executable)
    const workingDir = text(row.working_dir)
    return {
      title: 'Visual workbench',
      summary: text(row.errors, row.success === true ? 'Workbench prepared.' : 'Workbench failed.'),
      metrics: [
        { label: 'Result', value: passFail(row.success) },
        { label: 'Events', value: text(row.events, '0') },
        { label: 'Launched', value: row.launched ? 'yes' : 'no' },
      ],
      preview: [executable ? `Executable: ${executable}` : '', workingDir ? `Working dir: ${workingDir}` : '', text(row.errors)]
        .filter(Boolean)
        .join('\n'),
      artifacts: [],
    }
  }

  if (view === 'visual-review') {
    return {
      title: 'Visual review',
      summary: text(row.status, 'unknown'),
      metrics: [
        { label: 'Status', value: text(row.status, 'unknown') },
        { label: 'Blocking', value: row.blocking === false ? 'no' : 'yes' },
      ],
      preview: text(row.notes),
      artifacts: [],
    }
  }

  if (view === 'report' || view === 'artifacts') {
    const artifacts = artifactRows(row.artifacts)
    return {
      title: view === 'report' ? 'Report artifacts' : 'Artifact selection',
      summary: artifacts.length ? `${artifacts.length} artifacts available.` : 'No artifacts available.',
      metrics: [
        { label: 'Target', value: text(row.target, view) },
        { label: 'Artifacts', value: String(artifacts.length) },
      ],
      preview: '',
      artifacts,
    }
  }

  if (view === 'demo') {
    return {
      title: 'Demo template',
      summary: text(row.message, 'Use an explicit run request for production workflows.'),
      metrics: [{ label: 'Demo', value: text(row.demo, 'unknown') }],
      preview: text(row.command),
      artifacts: [],
    }
  }

  if (view === 'mode') {
    return {
      title: 'Composer mode',
      summary: 'Web workbench keeps composer controls visible.',
      metrics: [{ label: 'Mode', value: text(row.mode, 'ask') }],
      preview: '',
      artifacts: [],
    }
  }

  if (view === 'history' || view === 'exit') {
    return {
      title: view === 'history' ? 'Command history' : 'Exit workbench',
      summary: text(row.message),
      metrics: [],
      preview: '',
      artifacts: [],
    }
  }

  return null
}
