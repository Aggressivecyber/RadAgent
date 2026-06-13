from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:500,dy:500,dz:200}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'anchor', display_name:'Anchor', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:60,dz:20}, material_id:'Silicon', placement:{position:[-100,0,20]}, mother_volume:'world_volume'},
        {component_id:'box_b', display_name:'Box B', component_type:'layer', geometry_type:'box', dimensions:{dx:40,dy:40,dz:10}, material_id:'SiO2', placement:{position:[60,-80,-40]}, mother_volume:'world_volume'},
        {component_id:'poly', display_name:'Poly', component_type:'layer', geometry_type:'polycone', dimensions:{dx:20,dy:20,dz:10}, material_id:'Aluminum', placement:{position:[150,80,0]}, mother_volume:'world_volume',
          cross_section_polygon:[[150,80,0],[170,80,0],[170,100,0],[150,100,0]], cross_section_polygon_axes:{lateral:'x',depth:'y'}}
      ]}, '3d-align-controls');
      setViewAxes('x','y');
      const hasFn = typeof align3DSelection === 'function';
      const hasAxis = !!document.getElementById('align3dAxis');
      const hasFeature = !!document.getElementById('align3dFeature');
      const hasRef = !!document.getElementById('align3dRef');
      const hasPlaceFn = typeof place3DFeatureSelection === 'function';
      const hasPlaceTarget = !!document.getElementById('place3dTarget');
      if(hasFn && hasPlaceFn){
        selectedIds = new Set(['box_b','poly']);
        primaryId = 'box_b';
        document.getElementById('align3dAxis').value = 'z';
        document.getElementById('align3dFeature').value = 'max';
        document.getElementById('align3dRef').value = 'world';
        align3DSelection();
        const afterWorld = {
          b: bbox3D(model.components.find(c => c.component_id === 'box_b')),
          poly: bbox3D(model.components.find(c => c.component_id === 'poly')),
          world: bbox3D(model.components.find(c => c.component_id === 'world_volume')),
        };

        selectedIds = new Set(['anchor','box_b','poly']);
        primaryId = 'anchor';
        document.getElementById('align3dAxis').value = 'x';
        document.getElementById('align3dFeature').value = 'center';
        document.getElementById('align3dRef').value = 'primary';
        align3DSelection();
        const anchor = bbox3D(model.components.find(c => c.component_id === 'anchor'));
        const b = bbox3D(model.components.find(c => c.component_id === 'box_b'));
        const poly = bbox3D(model.components.find(c => c.component_id === 'poly'));
        selectedIds = new Set(['box_b','poly']);
        primaryId = 'box_b';
        document.getElementById('place3dAxis').value = 'z';
        document.getElementById('place3dFeature').value = 'min';
        document.getElementById('place3dTarget').value = '-20';
        place3DFeatureSelection();
        const placedB = bbox3D(model.components.find(c => c.component_id === 'box_b'));
        const placedPoly = bbox3D(model.components.find(c => c.component_id === 'poly'));
        return {
          hasFn, hasAxis, hasFeature, hasRef, hasPlaceFn, hasPlaceTarget,
          afterWorld,
          afterPrimary: {
            anchorCenterX: (anchor.min[0] + anchor.max[0]) / 2,
            bCenterX: (b.min[0] + b.max[0]) / 2,
            polyCenterX: (poly.min[0] + poly.max[0]) / 2,
            anchorPos: model.components.find(c => c.component_id === 'anchor').placement.position.slice(),
          },
          afterPlace: {bMinZ: placedB.min[2], polyMinZ: placedPoly.min[2]},
          selected: Array.from(selectedIds).sort(),
          historyPtr: history.ptr,
          issueCount: collectModelIssues().issues.length,
        };
      }
      return {hasFn, hasAxis, hasFeature, hasRef, hasPlaceFn, hasPlaceTarget};
    }"""
    )

    assert values["hasFn"], values
    assert values["hasAxis"], values
    assert values["hasFeature"], values
    assert values["hasRef"], values
    assert values["hasPlaceFn"], values
    assert values["hasPlaceTarget"], values
    assert abs(values["afterWorld"]["b"]["max"][2] - values["afterWorld"]["world"]["max"][2]) < 1e-9, values
    assert abs(values["afterWorld"]["poly"]["max"][2] - values["afterWorld"]["world"]["max"][2]) < 1e-9, values
    assert abs(values["afterPrimary"]["bCenterX"] - values["afterPrimary"]["anchorCenterX"]) < 1e-9, values
    assert abs(values["afterPrimary"]["polyCenterX"] - values["afterPrimary"]["anchorCenterX"]) < 1e-9, values
    assert values["afterPrimary"]["anchorPos"] == [-100, 0, 20], values
    assert abs(values["afterPlace"]["bMinZ"] - -20) < 1e-9, values
    assert abs(values["afterPlace"]["polyMinZ"] - -20) < 1e-9, values
    assert values["selected"] == ["box_b", "poly"], values
    assert values["historyPtr"] >= 3, values
    assert values["issueCount"] == 0, values
    print(values)


if __name__ == "__main__":
    main()
