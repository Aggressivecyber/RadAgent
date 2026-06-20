function jobScope(jobId = ''): string {
  const trimmed = jobId.trim()
  return trimmed ? ` --job=${trimmed}` : ''
}

export function buildConfirmationCommand(jobId = ''): string {
  return `/confirm${jobScope(jobId)} approve`
}

export function buildRejectCommand(reason: string, jobId = ''): string {
  const trimmed = reason.trim()
  return trimmed ? `/reject${jobScope(jobId)} ${trimmed}` : ''
}

export function buildAskMoreCommand(question: string, jobId = ''): string {
  const trimmed = question.trim()
  return trimmed ? `/ask-more${jobScope(jobId)} ${trimmed}` : ''
}
