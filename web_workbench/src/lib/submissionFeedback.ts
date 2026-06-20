export type SubmissionStatus = 'idle' | 'running' | 'paused' | 'success' | 'error'

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
      title: '正在仿真',
      detail: 'Agent 正在执行仿真工作流，状态会同步到侧边栏。',
    }
  }

  if (input.status === 'paused') {
    return {
      tone: 'paused',
      title: '等待审查',
      detail: '工作流停在参数核对或修复批准点，请在审查面板处理后继续。',
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
    detail: '输入仿真指令后启动工作流。',
  }
}
