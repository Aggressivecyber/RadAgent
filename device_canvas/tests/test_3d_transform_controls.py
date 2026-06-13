from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:1000,dy:1000,dz:1000}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'box_a', display_name:'Box A', component_type:'layer', geometry_type:'box', dimensions:{dx:100,dy:80,dz:20}, material_id:'Silicon', placement:{position:[0,0,0]}, mother_volume:'world_volume'},
        {component_id:'box_b', display_name:'Box B', component_type:'layer', geometry_type:'box', dimensions:{dx:40,dy:40,dz:10}, material_id:'SiO2', placement:{position:[200,0,0]}, mother_volume:'world_volume'},
        {component_id:'poly', display_name:'Poly', component_type:'layer', geometry_type:'polycone', dimensions:{dx:20,dy:20,dz:10}, material_id:'Aluminum', placement:{position:[300,0,0]}, mother_volume:'world_volume',
          cross_section_polygon:[[300,0,0],[320,0,0],[320,20,0],[300,20,0]], cross_section_polygon_axes:{lateral:'x',depth:'y'}}
      ]}, '3d-transform-controls');
      setViewAxes('x','y');

      const hasMoveFn = typeof move3DSelection === 'function';
      const hasSizeFn = typeof apply3DSizeToSelection === 'function';
      const hasCenterFn = typeof set3DCenterForSelection === 'function';
      const hasDx = !!document.getElementById('move3dDx');
      const hasTargetDz = !!document.getElementById('target3dDz');
      const hasCenterX = !!document.getElementById('center3dX');
      if(hasMoveFn && hasSizeFn && hasCenterFn){
        selectedIds = new Set(['box_a','box_b','poly']);
        primaryId = 'box_a';
        document.getElementById('move3dDx').value = '10';
        document.getElementById('move3dDy').value = '-5';
        document.getElementById('move3dDz').value = '7';
        move3DSelection();
        const afterMove = {
          a: model.components.find(c => c.component_id === 'box_a').placement.position.slice(),
          b: model.components.find(c => c.component_id === 'box_b').placement.position.slice(),
          polyPosition: model.components.find(c => c.component_id === 'poly').placement.position.slice(),
          polyFirst: model.components.find(c => c.component_id === 'poly').polygon[0].slice(),
        };

        selectedIds = new Set(['box_a','poly']);
        primaryId = 'box_a';
        document.getElementById('target3dDx').value = '120';
        document.getElementById('target3dDy').value = '90';
        document.getElementById('target3dDz').value = '30';
        apply3DSizeToSelection();
        const boxA = model.components.find(c => c.component_id === 'box_a');
        const poly = model.components.find(c => c.component_id === 'poly');
        selectedIds = new Set(['box_a']);
        primaryId = 'box_a';
        document.getElementById('center3dX').value = '100';
        document.getElementById('center3dY').value = '-5';
        document.getElementById('center3dZ').value = '50';
        set3DCenterForSelection();
        selectedIds = new Set(['poly']);
        primaryId = 'poly';
        document.getElementById('center3dX').value = '300';
        document.getElementById('center3dY').value = '';
        document.getElementById('center3dZ').value = '50';
        set3DCenterForSelection();
        const afterCenter = {
          boxPos: model.components.find(c => c.component_id === 'box_a').placement.position.slice(),
          polyBox: bbox3D(model.components.find(c => c.component_id === 'poly')),
          polyPos: model.components.find(c => c.component_id === 'poly').placement.position.slice(),
        };
        selectedIds = new Set(['box_a','poly']);
        primaryId = 'box_a';
        return {
          hasMoveFn, hasSizeFn, hasCenterFn, hasDx, hasTargetDz, hasCenterX, afterMove,
          afterSize: {dims: {...boxA.dimensions}, polyDims: {...poly.dimensions}},
          afterCenter,
          selected: Array.from(selectedIds).sort(),
          historyPtr: history.ptr,
          issueCount: collectModelIssues().issues.length,
        };
      }
      return {hasMoveFn, hasSizeFn, hasCenterFn, hasDx, hasTargetDz, hasCenterX};
    }"""
    )

    assert values["hasMoveFn"], values
    assert values["hasSizeFn"], values
    assert values["hasCenterFn"], values
    assert values["hasDx"], values
    assert values["hasTargetDz"], values
    assert values["hasCenterX"], values
    assert values["afterMove"]["a"] == [10, -5, 7], values
    assert values["afterMove"]["b"] == [210, -5, 7], values
    assert values["afterMove"]["polyPosition"] == [310, -5, 7], values
    assert values["afterMove"]["polyFirst"] == [310, -5, 7], values
    assert values["afterSize"]["dims"] == {"dx": 120, "dy": 90, "dz": 30}, values
    assert values["afterSize"]["polyDims"] == {"dx": 20, "dy": 20, "dz": 10}, values
    assert values["afterCenter"]["boxPos"] == [100, -5, 50], values
    poly_box = values["afterCenter"]["polyBox"]
    assert abs((poly_box["min"][0] + poly_box["max"][0]) / 2 - 300) < 1e-9, values
    assert abs((poly_box["min"][1] + poly_box["max"][1]) / 2 - 5) < 1e-9, values
    assert abs((poly_box["min"][2] + poly_box["max"][2]) / 2 - 50) < 1e-9, values
    assert values["afterCenter"]["polyPos"] == [290, -5, 50], values
    assert values["selected"] == ["box_a", "poly"], values
    assert values["historyPtr"] >= 4, values
    assert values["issueCount"] == 0, values
    print(values)


if __name__ == "__main__":
    main()
