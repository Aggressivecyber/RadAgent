from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:100,dy:100,dz:100}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'edge', display_name:'Edge Box', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'Silicon', placement:{position:[35,0,0]}, mother_volume:'world_volume'},
        {component_id:'array_src', display_name:'Array Source', component_type:'layer', geometry_type:'box', dimensions:{dx:10,dy:10,dz:10}, material_id:'SiO2', placement:{position:[-35,0,0]}, mother_volume:'world_volume'},
        {component_id:'poly', display_name:'Poly', component_type:'layer', geometry_type:'polycone', dimensions:{dx:10,dy:10,dz:10}, material_id:'Aluminum', placement:{position:[0,20,0]}, mother_volume:'world_volume',
          cross_section_polygon:[[0,20,0],[10,20,0],[10,30,0],[0,30,0]], cross_section_polygon_axes:{lateral:'x',depth:'y'}}
      ]}, 'safe-copy-array');
      setViewAxes('x','y');

      selectedIds = new Set(['edge']);
      primaryId = 'edge';
      duplicateSelected();
      const afterBlockedDuplicate = {
        ids: model.components.map(c => c.component_id).sort(),
        selected: Array.from(selectedIds).sort(),
        issues: collectModelIssues().issues.map(i => i.code),
      };

      document.getElementById('constrain3dWorld').checked = false;
      duplicateSelected();
      const freeCopy = model.components.find(c => c.component_id.startsWith('edge_copy'));
      const afterFreeDuplicate = {
        copyPos: freeCopy && freeCopy.placement.position.slice(),
        evidence: freeCopy && freeCopy.source_evidence,
        issues: collectModelIssues().issues.map(i => i.code),
      };

      document.getElementById('constrain3dWorld').checked = true;
      selectedIds = new Set(['array_src']);
      primaryId = 'array_src';
      document.getElementById('arrayCount').value = '6';
      document.getElementById('arrayDx').value = '20';
      document.getElementById('arrayDy').value = '0';
      arrayDuplicateSelection();
      const arrayCopies = model.components
        .filter(c => c.component_id.startsWith('array_src_arr'))
        .sort((a,b) => a.component_id.localeCompare(b.component_id));
      const afterArray = {
        ids: arrayCopies.map(c => c.component_id),
        positions: arrayCopies.map(c => c.placement.position.slice()),
        evidence: arrayCopies.map(c => c.source_evidence),
        issues: collectModelIssues().issues.map(i => i.code),
      };

      selectedIds = new Set(['poly']);
      primaryId = 'poly';
      document.getElementById('constrain3dWorld').checked = true;
      duplicateSelected();
      const polyCopy = model.components.find(c => c.component_id.startsWith('poly_copy'));
      const afterPolyCopy = {
        pos: polyCopy && polyCopy.placement.position.slice(),
        box: polyCopy && bbox3D(polyCopy),
        evidence: polyCopy && polyCopy.source_evidence,
      };

      return {afterBlockedDuplicate, afterFreeDuplicate, afterArray, afterPolyCopy};
    }"""
    )

    assert "edge_copy" not in values["afterBlockedDuplicate"]["ids"], values
    assert values["afterBlockedDuplicate"]["selected"] == ["edge"], values
    assert "outside_world" not in values["afterBlockedDuplicate"]["issues"], values
    assert values["afterFreeDuplicate"]["copyPos"] == [45, 10, 0], values
    assert any("duplicate_of:edge" in item for item in values["afterFreeDuplicate"]["evidence"]), values
    assert "outside_world" in values["afterFreeDuplicate"]["issues"], values

    assert values["afterArray"]["ids"] == ["array_src_arr2", "array_src_arr3", "array_src_arr4", "array_src_arr5"], values
    assert values["afterArray"]["positions"] == [[-15, 0, 0], [5, 0, 0], [25, 0, 0], [45, 0, 0]], values
    for evidence in values["afterArray"]["evidence"]:
        assert any("array_of:array_src" in item for item in evidence), values
    assert values["afterArray"]["issues"].count("outside_world") == 1, values

    assert values["afterPolyCopy"]["pos"] == [10, 30, 0], values
    assert values["afterPolyCopy"]["box"]["min"][0] == 10, values
    assert any("duplicate_of:poly" in item for item in values["afterPolyCopy"]["evidence"]), values
    print(values)


if __name__ == "__main__":
    main()
