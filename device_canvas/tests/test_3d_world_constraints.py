from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:100,dy:100,dz:100}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'edge', display_name:'Edge Box', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'Silicon', placement:{position:[35,0,0]}, mother_volume:'world_volume'},
        {component_id:'small', display_name:'Small Box', component_type:'layer', geometry_type:'box', dimensions:{dx:10,dy:10,dz:10}, material_id:'SiO2', placement:{position:[0,0,0]}, mother_volume:'world_volume'},
        {component_id:'poly', display_name:'Poly', component_type:'layer', geometry_type:'polycone', dimensions:{dx:10,dy:10,dz:10}, material_id:'Aluminum', placement:{position:[0,20,0]}, mother_volume:'world_volume',
          cross_section_polygon:[[0,20,0],[10,20,0],[10,30,0],[0,30,0]], cross_section_polygon_axes:{lateral:'x',depth:'y'}}
      ]}, 'world-constraint-controls');
      setViewAxes('x','y');
      const hasToggle = !!document.getElementById('constrain3dWorld');
      const toggleDefault = hasToggle ? document.getElementById('constrain3dWorld').checked : null;

      selectedIds = new Set(['edge']);
      primaryId = 'edge';
      document.getElementById('move3dDx').value = '10';
      document.getElementById('move3dDy').value = '0';
      document.getElementById('move3dDz').value = '0';
      move3DSelection();
      const afterBlockedMove = model.components.find(c => c.component_id === 'edge').placement.position.slice();
      const issuesAfterBlockedMove = collectModelIssues().issues.map(i => i.code);

      if(hasToggle)document.getElementById('constrain3dWorld').checked = false;
      move3DSelection();
      const afterFreeMove = model.components.find(c => c.component_id === 'edge').placement.position.slice();
      const issuesAfterFreeMove = collectModelIssues().issues.map(i => i.code);

      if(hasToggle)document.getElementById('constrain3dWorld').checked = true;
      selectedIds = new Set(['small']);
      primaryId = 'small';
      document.getElementById('target3dDx').value = '120';
      document.getElementById('target3dDy').value = '20';
      document.getElementById('target3dDz').value = '20';
      apply3DSizeToSelection();
      const sizeAfterBlocked = {...model.components.find(c => c.component_id === 'small').dimensions};

      document.getElementById('center3dX').value = '49';
      document.getElementById('center3dY').value = '';
      document.getElementById('center3dZ').value = '';
      set3DCenterForSelection();
      const centerAfterBlocked = model.components.find(c => c.component_id === 'small').placement.position.slice();

      selectedIds = new Set(['small']);
      primaryId = 'small';
      document.getElementById('align3dAxis').value = 'x';
      document.getElementById('align3dFeature').value = 'max';
      document.getElementById('align3dRef').value = 'world';
      align3DSelection();
      const alignAfterAllowed = bbox3D(model.components.find(c => c.component_id === 'small'));

      selectedIds = new Set(['small']);
      primaryId = 'small';
      document.getElementById('place3dAxis').value = 'x';
      document.getElementById('place3dFeature').value = 'center';
      document.getElementById('place3dTarget').value = '-49';
      place3DFeatureSelection();
      const placeAfterBlocked = model.components.find(c => c.component_id === 'small').placement.position.slice();

      selectedIds = new Set(['poly']);
      primaryId = 'poly';
      document.getElementById('center3dX').value = '-49';
      document.getElementById('center3dY').value = '';
      document.getElementById('center3dZ').value = '';
      set3DCenterForSelection();
      const polyAfterBlocked = {
        pos: model.components.find(c => c.component_id === 'poly').placement.position.slice(),
        box: bbox3D(model.components.find(c => c.component_id === 'poly')),
      };

      const exported = buildDeviceCanvasState();
      return {
        hasToggle, toggleDefault, afterBlockedMove, issuesAfterBlockedMove,
        afterFreeMove, issuesAfterFreeMove, sizeAfterBlocked, centerAfterBlocked,
        alignAfterAllowed, placeAfterBlocked, polyAfterBlocked,
        exportedTransform: exported.transform,
      };
    }"""
    )

    assert values["hasToggle"], values
    assert values["toggleDefault"] is True, values
    assert values["afterBlockedMove"] == [35, 0, 0], values
    assert "outside_world" not in values["issuesAfterBlockedMove"], values
    assert values["afterFreeMove"] == [45, 0, 0], values
    assert "outside_world" in values["issuesAfterFreeMove"], values
    assert values["sizeAfterBlocked"] == {"dx": 10, "dy": 10, "dz": 10}, values
    assert values["centerAfterBlocked"] == [0, 0, 0], values
    assert abs(values["alignAfterAllowed"]["max"][0] - 50) < 1e-9, values
    assert values["placeAfterBlocked"] == [45, 0, 0], values
    assert values["polyAfterBlocked"]["pos"] == [0, 20, 0], values
    assert values["polyAfterBlocked"]["box"]["min"][0] == 0, values
    assert values["exportedTransform"] == {"constrainWorld": True, "boundaryMode": "block"}, values
    print(values)


if __name__ == "__main__":
    main()
