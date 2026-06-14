import { FileText, FolderOpen, PanelRightOpen } from 'lucide-react'
import type { ArtifactContent } from '../lib/api'
import type { AgentCockpit } from '../lib/workbenchPresentation'

type ArtifactWorkspaceProps = {
  cockpit: AgentCockpit
  selectedArtifact: ArtifactContent | null
  loading: boolean
  error: string
  onSelectArtifact: (path: string) => void
  onOpenInspector: () => void
}

function previewText(artifact: ArtifactContent | null): string {
  if (!artifact) {
    return '选择左侧文件查看当前内容、类型和截断状态。'
  }
  if (!artifact.exists) {
    return '文件当前不存在，可能尚未生成或已被移动。'
  }
  if (artifact.kind === 'binary') {
    return '二进制文件暂不在浏览器内预览，可通过本地工作区打开。'
  }
  return artifact.text || JSON.stringify(artifact.json_data ?? {}, null, 2)
}

export default function ArtifactWorkspace({
  cockpit,
  selectedArtifact,
  loading,
  error,
  onSelectArtifact,
  onOpenInspector,
}: ArtifactWorkspaceProps) {
  const hasFiles = cockpit.fileGroups.some((group) => group.files.length > 0)
  const preview = previewText(selectedArtifact)

  return (
    <aside className="artifact-workspace">
      <header className="artifact-workspace-header">
        <div>
          <span>文件与产物</span>
          <strong>Files</strong>
        </div>
        <button type="button" onClick={onOpenInspector} title="打开审查面板">
          <PanelRightOpen size={16} />
          <span>审查</span>
        </button>
      </header>

      <section className="artifact-tree" aria-label="Agent created files">
        {hasFiles ? (
          cockpit.fileGroups.map((group) => (
            <div className="artifact-group" key={group.id}>
              <div className="artifact-group-title">
                <FolderOpen size={15} />
                <span>{group.label}</span>
                <small>{group.labelEn}</small>
              </div>
              <div className="artifact-file-list">
                {group.files.map((file) => (
                  <button
                    className={file.selected ? 'selected' : ''}
                    type="button"
                    key={file.path}
                    onClick={() => onSelectArtifact(file.path)}
                    title={file.path}
                  >
                    <FileText size={15} />
                    <span>
                      <strong>{file.name}</strong>
                      <small>
                        {file.kindLabel}
                        {file.sizeLabel ? ` · ${file.sizeLabel}` : ''}
                      </small>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))
        ) : (
          <p className="artifact-empty">Agent 运行后会在这里显示创建的文件、日志和报告。</p>
        )}
      </section>

      <section className="artifact-preview-pane" aria-label="Selected artifact preview">
        <div className="artifact-preview-heading">
          <span>{loading ? '加载中' : selectedArtifact?.kind || 'preview'}</span>
          <strong>{selectedArtifact?.path.split('/').filter(Boolean).at(-1) || '未选择文件'}</strong>
        </div>
        {error ? <p className="artifact-error">{error}</p> : null}
        <pre>{preview}</pre>
      </section>
    </aside>
  )
}
