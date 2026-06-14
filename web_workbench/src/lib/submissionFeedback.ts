export type SubmissionStatus = 'idle' | 'running' | 'success' | 'error'

export type SubmissionFeedbackInput = {
  status: SubmissionStatus
  command?: string
  message?: string
}

export type SubmissionFeedback = {
  tone: SubmissionStatus
  title: string
  detail: string
}

export function createSubmissionFeedback(input: SubmissionFeedbackInput): SubmissionFeedback {
  if (input.status === 'running') {
    return {
      tone: 'running',
      title: '任务已提交',
      detail: '正在启动工作流，Agent 会先规划模型并写入时间线。',
    }
  }

  if (input.status === 'success') {
    return {
      tone: 'success',
      title: '工作流已启动',
      detail: input.message || '请求已被服务接收，后续事件会进入 Agent 时间线。',
    }
  }

  if (input.status === 'error') {
    return {
      tone: 'error',
      title: '提交失败',
      detail: input.message || '请求未能送达服务，请检查本地环境和模型配置。',
    }
  }

  return {
    tone: 'idle',
    title: '等待提交',
    detail: '选择任务模板、源项和材料后启动 Agent。',
  }
}
