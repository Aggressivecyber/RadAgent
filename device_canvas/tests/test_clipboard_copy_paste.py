from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:100,dy:100,dz:100}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'box', display_name:'Box', component_type:'layer', geometry_type:'box', dimensions:{dx:10,dy:10,dz:10}, material_id:'Silicon', placement:{position:[0,0,0]}, mother_volume:'world_volume'},
        {component_id:'poly', display_name:'Poly', component_type:'layer', geometry_type:'polycone', dimensions:{dx:10,dy:10,dz:10}, material_id:'Aluminum', placement:{position:[10,10,0]}, mother_volume:'world_volume',
          cross_section_polygon:[[10,10,0],[20,10,0],[20,20,0],[10,20,0]], cross_section_polygon_axes:{lateral:'x',depth:'y'}},
        {component_id:'edge', display_name:'Edge', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:10}, material_id:'SiO2', placement:{position:[35,0,0]}, mother_volume:'world_volume'}
      ]}, 'clipboard-copy-paste');
      setViewAxes('x','y');
      const hasCopy = typeof copySelectionToClipboard === 'function';
      const hasPaste = typeof pasteClipboardSelection === 'function';
      const hasCopyBtn = !!document.querySelector('[data-action="copy-selection"]');
      const hasPasteBtn = !!document.querySelector('[data-action="paste-selection"]');

      selectedIds = new Set(['box','poly']);
      primaryId = 'box';
      copySelectionToClipboard();
      const copied = {
        count: componentClipboard.items.length,
        ids: componentClipboard.items.map(item => item.component_id).sort(),
      };
      pasteClipboardSelection();
      const pasted = model.components
        .filter(c => c.source_evidence && c.source_evidence.some(v => v.includes('clipboard_of:')))
        .sort((a,b) => a.component_id.localeCompare(b.component_id));
      const afterPaste = {
        ids: pasted.map(c => c.component_id),
        positions: pasted.map(c => c.placement.position.slice()),
        polyBox: bbox3D(pasted.find(c => c.component_id.startsWith('poly_paste'))),
        evidence: pasted.map(c => c.source_evidence),
        selected: Array.from(selectedIds).sort(),
      };

      selectedIds = new Set(['edge']);
      primaryId = 'edge';
      copySelectionToClipboard();
      pasteClipboardSelection();
      const afterBlockedPaste = {
        edgePasteCount: model.components.filter(c => c.component_id.startsWith('edge_paste')).length,
        selected: Array.from(selectedIds).sort(),
        issues: collectModelIssues().issues.map(i => i.code),
      };

      document.getElementById('constrain3dWorld').checked = false;
      pasteClipboardSelection();
      const edgePaste = model.components.find(c => c.component_id.startsWith('edge_paste'));
      const afterFreePaste = {
        pos: edgePaste && edgePaste.placement.position.slice(),
        evidence: edgePaste && edgePaste.source_evidence,
        issues: collectModelIssues().issues.map(i => i.code),
      };

      return {hasCopy, hasPaste, hasCopyBtn, hasPasteBtn, copied, afterPaste, afterBlockedPaste, afterFreePaste};
    }"""
    )

    assert values["hasCopy"], values
    assert values["hasPaste"], values
    assert values["hasCopyBtn"], values
    assert values["hasPasteBtn"], values
    assert values["copied"] == {"count": 2, "ids": ["box", "poly"]}, values
    assert values["afterPaste"]["ids"] == ["box_paste", "poly_paste"], values
    assert values["afterPaste"]["positions"] == [[10, 10, 0], [20, 20, 0]], values
    assert values["afterPaste"]["polyBox"]["min"][:2] == [20, 20], values
    for evidence in values["afterPaste"]["evidence"]:
        assert any("clipboard_of:" in item for item in evidence), values
    assert values["afterPaste"]["selected"] == ["box_paste", "poly_paste"], values

    assert values["afterBlockedPaste"]["edgePasteCount"] == 0, values
    assert values["afterBlockedPaste"]["selected"] == ["edge"], values
    assert "outside_world" not in values["afterBlockedPaste"]["issues"], values
    assert values["afterFreePaste"]["pos"] == [45, 10, 0], values
    assert any("clipboard_of:edge" in item for item in values["afterFreePaste"]["evidence"]), values
    assert "outside_world" in values["afterFreePaste"]["issues"], values
    print(values)


if __name__ == "__main__":
    main()
