from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:100,dy:100,dz:100}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'edge', display_name:'Edge Box', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'Silicon', placement:{position:[35,0,0]}, mother_volume:'world_volume'},
        {component_id:'center', display_name:'Center Box', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'SiO2', placement:{position:[0,0,0]}, mother_volume:'world_volume'},
        {component_id:'poly', display_name:'Poly', component_type:'layer', geometry_type:'polycone', dimensions:{dx:10,dy:10,dz:10}, material_id:'Aluminum', placement:{position:[35,20,0]}, mother_volume:'world_volume',
          cross_section_polygon:[[35,20,0],[45,20,0],[45,30,0],[35,30,0]], cross_section_polygon_axes:{lateral:'x',depth:'y'}}
      ]}, '2d-edit-constraint-controls');
      setViewAxes('x','y');

      selectedIds = new Set(['edge']);
      primaryId = 'edge';
      document.getElementById('nudgeStep').value = '10';
      nudgeSelection(1,0);
      const afterBlockedNudge = model.components.find(c => c.component_id === 'edge').placement.position.slice();
      const issuesAfterBlockedNudge = collectModelIssues().issues.map(i => i.code);

      document.getElementById('constrain3dWorld').checked = false;
      nudgeSelection(1,0);
      const afterFreeNudge = model.components.find(c => c.component_id === 'edge').placement.position.slice();
      const issuesAfterFreeNudge = collectModelIssues().issues.map(i => i.code);

      document.getElementById('constrain3dWorld').checked = true;
      selectedIds = new Set(['center']);
      primaryId = 'center';
      document.getElementById('targetLatSize').value = '120';
      document.getElementById('targetDepSize').value = '20';
      fitSelectionToInputs();
      const afterBlockedFit = {...model.components.find(c => c.component_id === 'center').dimensions};

      const center = model.components.find(c => c.component_id === 'center');
      let centerNode = rectNodes.get('center').shape;
      centerNode.scaleX(6);
      onShapeTransform(center);
      const afterBlockedHandleScale = {
        dims: {...center.dimensions},
        nodeScale: {x: centerNode.scaleX(), y: centerNode.scaleY()},
        nodeSize: {w: centerNode.width(), h: centerNode.height()},
      };

      centerNode = rectNodes.get('center').shape;
      centerNode.x(X(45) - centerNode.width() / 2);
      centerNode.y(Y(0) - centerNode.height() / 2);
      onShapeDrag(center);
      const afterBlockedDrag = center.placement.position.slice();

      const poly = model.components.find(c => c.component_id === 'poly');
      const polyNode = rectNodes.get('poly').shape;
      polyNode.position({x:20 * camera.sLat, y:0});
      onShapeDragEnd(poly);
      const afterBlockedPolyDrag = {
        pos: poly.placement.position.slice(),
        box: bbox3D(poly),
        visualOffset: {x: polyNode.x(), y: polyNode.y()},
      };

      return {
        afterBlockedNudge,
        issuesAfterBlockedNudge,
        afterFreeNudge,
        issuesAfterFreeNudge,
        afterBlockedFit,
        afterBlockedHandleScale,
        afterBlockedDrag,
        afterBlockedPolyDrag,
      };
    }"""
    )

    assert values["afterBlockedNudge"] == [35, 0, 0], values
    assert "outside_world" not in values["issuesAfterBlockedNudge"], values
    assert values["afterFreeNudge"] == [45, 0, 0], values
    assert "outside_world" in values["issuesAfterFreeNudge"], values
    assert values["afterBlockedFit"] == {"dx": 20, "dy": 20, "dz": 20}, values
    assert values["afterBlockedHandleScale"]["dims"] == {"dx": 20, "dy": 20, "dz": 20}, values
    assert values["afterBlockedHandleScale"]["nodeScale"] == {"x": 1, "y": 1}, values
    assert values["afterBlockedDrag"] == [0, 0, 0], values
    assert values["afterBlockedPolyDrag"]["pos"] == [35, 20, 0], values
    assert values["afterBlockedPolyDrag"]["box"]["max"][0] == 45, values
    assert values["afterBlockedPolyDrag"]["visualOffset"] == {"x": 0, "y": 0}, values
    print(values)


if __name__ == "__main__":
    main()
