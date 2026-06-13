from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:100,dy:100,dz:100}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'edge', display_name:'Edge Box', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'Silicon', placement:{position:[35,0,0]}, mother_volume:'world_volume'},
        {component_id:'drag_box', display_name:'Drag Box', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'SiO2', placement:{position:[0,0,0]}, mother_volume:'world_volume'}
      ]}, 'boundary-clamp-mode');
      setViewAxes('x','y');
      const modeEl = document.getElementById('constraintBoundaryMode');
      const hasClampHelpers = {
        modeEl: !!modeEl,
        clampFn: typeof clampTranslationToContainer === 'function',
        syncFn: typeof syncTransformConstraintFromUI === 'function',
      };

      selectedIds = new Set(['edge']);
      primaryId = 'edge';
      document.getElementById('nudgeStep').value = '10';
      nudgeSelection(1,0);
      const afterDefaultBlock = model.components.find(c => c.component_id === 'edge').placement.position.slice();

      modeEl.value = 'clamp';
      syncTransformConstraintFromUI();
      nudgeSelection(1,0);
      const afterClampNudge = model.components.find(c => c.component_id === 'edge').placement.position.slice();
      const boxAfterClampNudge = bbox3D(model.components.find(c => c.component_id === 'edge'));

      model.components.find(c => c.component_id === 'edge').placement.position = [35,0,0];
      document.getElementById('move3dDx').value = '20';
      document.getElementById('move3dDy').value = '0';
      document.getElementById('move3dDz').value = '0';
      move3DSelection();
      const afterClamp3DMove = model.components.find(c => c.component_id === 'edge').placement.position.slice();

      const drag = model.components.find(c => c.component_id === 'drag_box');
      selectOnly('drag_box');
      const node = rectNodes.get('drag_box').shape;
      node.x(X(46) - node.width()/2);
      node.y(Y(0) - node.height()/2);
      onShapeDrag(drag);
      const afterClampDrag = {
        pos: drag.placement.position.slice(),
        visualCenterX: toDataX(node.x()+node.width()/2),
        box: bbox3D(drag),
      };

      const exported = buildDeviceCanvasState().transform;
      transformSettings.boundaryMode = 'block';
      modeEl.value = 'block';
      applyDeviceCanvasState({transform: exported});
      updateTransformConstraintUI();
      const restored = {
        mode: transformSettings.boundaryMode,
        modeEl: document.getElementById('constraintBoundaryMode').value,
      };

      document.getElementById('constrain3dWorld').checked = false;
      syncTransformConstraintFromUI();
      selectedIds = new Set(['edge']);
      primaryId = 'edge';
      model.components.find(c => c.component_id === 'edge').placement.position = [35,0,0];
      document.getElementById('move3dDx').value = '20';
      move3DSelection();
      const afterConstraintOff = model.components.find(c => c.component_id === 'edge').placement.position.slice();

      return {hasClampHelpers, afterDefaultBlock, afterClampNudge, boxAfterClampNudge, afterClamp3DMove, afterClampDrag, exported, restored, afterConstraintOff};
    }"""
    )

    assert all(values["hasClampHelpers"].values()), values
    assert values["afterDefaultBlock"] == [35, 0, 0], values
    assert values["afterClampNudge"] == [40, 0, 0], values
    assert values["boxAfterClampNudge"]["max"][0] == 50, values
    assert values["afterClamp3DMove"] == [40, 0, 0], values
    assert values["afterClampDrag"]["pos"] == [40, 0, 0], values
    assert abs(values["afterClampDrag"]["visualCenterX"] - 40) < 1e-9, values
    assert values["afterClampDrag"]["box"]["max"][0] == 50, values
    assert values["exported"] == {"constrainWorld": True, "boundaryMode": "clamp"}, values
    assert values["restored"] == {"mode": "clamp", "modeEl": "clamp"}, values
    assert values["afterConstraintOff"] == [55, 0, 0], values
    print(values)


if __name__ == "__main__":
    main()
