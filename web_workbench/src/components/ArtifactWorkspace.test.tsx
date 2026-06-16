import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import ArtifactWorkspace from './ArtifactWorkspace'
import type { ArtifactContent } from '../lib/api'
import type { AgentCockpit } from '../lib/workbenchPresentation'

const cockpit: AgentCockpit = {
  agent: {
    stateLabel: '运行中',
    phaseLabel: '工程生成',
    currentAction: 'Files persisted',
    workspace: '/tmp/job',
    changedFiles: '2 个文件',
    statusChips: [],
  },
  fileGroups: [
    {
      id: 'g4_codegen',
      label: '工程生成',
      labelEn: 'Codegen',
      files: [
        {
          path: '/tmp/job/05_codegen/proposed_patch.json',
          name: 'proposed_patch.json',
          stage: 'g4_codegen',
          kindLabel: 'JSON',
          sizeLabel: '4 KB',
          selected: false,
        },
      ],
    },
    {
      id: 'patch',
      label: '修订补丁',
      labelEn: 'Patch',
      files: [
        {
          path: '/tmp/job/06_patch/geant4_project/src/DetectorConstruction.cc',
          name: 'DetectorConstruction.cc',
          stage: 'patch',
          kindLabel: '源码',
          sizeLabel: '8 KB',
          selected: true,
        },
      ],
    },
  ],
  recentActivity: [],
  llmDebugCalls: [],
  runtimeActive: true,
}

const selectedArtifact: ArtifactContent = {
  path: '/tmp/job/06_patch/geant4_project/src/DetectorConstruction.cc',
  exists: true,
  kind: 'text',
  text: '#include "DetectorConstruction.hh"',
  json_data: null,
  size_bytes: 8192,
  truncated: false,
  errors: [],
}

describe('ArtifactWorkspace', () => {
  it('renders grouped created files and selected file preview', () => {
    const markup = renderToStaticMarkup(
      <ArtifactWorkspace
        cockpit={cockpit}
        selectedArtifact={selectedArtifact}
        loading={false}
        error=""
        onSelectArtifact={() => {}}
        onOpenInspector={() => {}}
      />,
    )

    expect(markup).toContain('文件与产物')
    expect(markup).toContain('工程生成')
    expect(markup).toContain('修订补丁')
    expect(markup).toContain('proposed_patch.json')
    expect(markup).toContain('DetectorConstruction.cc')
    expect(markup).toContain('源码')
    expect(markup).toContain('8 KB')
    expect(markup).toContain('#include &quot;DetectorConstruction.hh&quot;')
  })

  it('renders a staged artifact waiting state before files are created', () => {
    const emptyCockpit: AgentCockpit = {
      ...cockpit,
      fileGroups: [],
    }

    const markup = renderToStaticMarkup(
      <ArtifactWorkspace
        cockpit={emptyCockpit}
        selectedArtifact={null}
        loading={false}
        error=""
        onSelectArtifact={() => {}}
        onOpenInspector={() => {}}
      />,
    )

    expect(markup).toContain('等待 Agent 产物')
    expect(markup).toContain('Geant4 源码')
    expect(markup).toContain('运行日志')
    expect(markup).toContain('门禁摘要')
    expect(markup).toContain('结果报告')
    expect(markup).toContain('产物生成后会在这里按阶段归档。')
  })
})
