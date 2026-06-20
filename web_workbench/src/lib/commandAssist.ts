export function buildRunCommand(request: string): string {
  const trimmed = request.trim()
  return trimmed ? `/run ${trimmed}` : ''
}

export function buildSimulateCommand(events: number, jobId = ''): string {
  const safeEvents = Number.isFinite(events) && events > 0 ? Math.floor(events) : 1
  const targetJob = jobId.trim()
  return targetJob ? `/simulate ${safeEvents} ${targetJob}` : `/simulate ${safeEvents}`
}

export function composeCommandTemplate(command: string): string {
  const name = command.trim().replace(/^\//, '').split(/\s+/)[0]
  if (name === 'run') {
    return '/run Describe the simulation you want to build'
  }
  if (name === 'simulate') {
    return '/simulate 1000'
  }
  return name ? `/${name}` : ''
}
