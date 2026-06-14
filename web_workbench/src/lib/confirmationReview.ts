export type ConfirmationReviewItem = {
  title: string
  detail: string
  meta: string
}

export type ConfirmationReviewView = {
  status: string
  actionable: boolean
  summary: string
  missingInformation: string[]
  criticalConfirmations: ConfirmationReviewItem[]
  questions: ConfirmationReviewItem[]
  preview: string
}

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

function itemFromCritical(value: unknown, index: number): ConfirmationReviewItem {
  const item = asRecord(value)
  return {
    title: text(item.field_path, `确认项 ${index + 1}`),
    detail: text(item.impact || item.reason || item.proposed_value),
    meta: text(item.category || item.proposed_value),
  }
}

function itemFromQuestion(value: unknown, index: number): ConfirmationReviewItem {
  const item = asRecord(value)
  return {
    title: text(item.question || item.field_path, `问题 ${index + 1}`),
    detail: text(item.impact || item.reason),
    meta: text(item.proposed_value || item.category || item.field_path),
  }
}

export function createConfirmationReviewView(data: unknown): ConfirmationReviewView {
  const review = asRecord(data)
  const request = asRecord(review.confirmation_request || review.request)
  const proposal = asRecord(review.proposed_model_completion || review.proposal)
  const summary = text(
    review.summary_for_user || request.summary_for_user || review.summary,
    '请确认本轮 Geant4 模型假设、关键参数和继续执行条件。',
  )
  const status = text(review.status, 'pending')

  return {
    status,
    actionable: !['approved', 'rejected'].includes(status),
    summary,
    missingInformation: [
      ...asArray(review.missing_information),
      ...asArray(request.missing_information),
      ...asArray(proposal.missing_information),
    ].map((item) => text(item)).filter(Boolean),
    criticalConfirmations: [
      ...asArray(review.critical_confirmations),
      ...asArray(request.critical_confirmations),
    ].map(itemFromCritical),
    questions: [
      ...asArray(review.questions),
      ...asArray(request.questions),
    ].map(itemFromQuestion),
    preview: text(review.preview),
  }
}
