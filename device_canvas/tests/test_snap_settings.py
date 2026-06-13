from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:300,dy:300,dz:100}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'anchor', display_name:'Anchor', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'Silicon', placement:{position:[0,0,0]}, mother_volume:'world_volume'},
        {component_id:'moving', display_name:'Moving', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'SiO2', placement:{position:[55,0,0]}, mother_volume:'world_volume'}
      ]}, 'snap-settings');
      setViewAxes('x','y');
      const hasCompToggle = !!document.getElementById('snapComponents');
      const hasGridToggle = !!document.getElementById('snapGrid');
      const hasCanvasToggle = !!document.getElementById('snapCanvas');
      const hasOriginLat = !!document.getElementById('gridOriginLat');
      const hasOriginDep = !!document.getElementById('gridOriginDep');
      const hasSettings = typeof snapSettings === 'object';
      const moving = model.components.find(c => c.component_id === 'moving');

      document.getElementById('snapOn').checked = true;
      document.getElementById('snapPx').value = '80';
      document.getElementById('gridStep').value = '0';
      if(hasCompToggle)document.getElementById('snapComponents').checked = true;
      if(hasGridToggle)document.getElementById('snapGrid').checked = false;
      if(hasCanvasToggle)document.getElementById('snapCanvas').checked = false;
      onSnapSettingsChange();
      let node = rectNodes.get('moving').shape;
      node.x(X(31) - node.width() / 2);
      node.y(Y(0) - node.height() / 2);
      onShapeDrag(moving);
      const afterComponentSnap = moving.placement.position.slice();

      if(hasCompToggle)document.getElementById('snapComponents').checked = false;
      onSnapSettingsChange();
      node = rectNodes.get('moving').shape;
      node.x(X(31) - node.width() / 2);
      node.y(Y(0) - node.height() / 2);
      onShapeDrag(moving);
      const afterComponentDisabled = moving.placement.position.slice();

      document.getElementById('gridStep').value = '25';
      if(hasOriginLat)document.getElementById('gridOriginLat').value = '5';
      if(hasOriginDep)document.getElementById('gridOriginDep').value = '-10';
      if(hasGridToggle)document.getElementById('snapGrid').checked = true;
      onSnapSettingsChange();
      node = rectNodes.get('moving').shape;
      node.x(X(36) - node.width() / 2);
      node.y(Y(0) - node.height() / 2);
      onShapeDrag(moving);
      const afterGridSnap = moving.placement.position.slice();

      if(hasCanvasToggle)document.getElementById('snapCanvas').checked = true;
      document.getElementById('snapPx').value = '50';
      onSnapSettingsChange();
      const exported = buildDeviceCanvasState().snap;

      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:300,dy:300,dz:100}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'moving', display_name:'Moving', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'SiO2', placement:{position:[0,0,0]}, mother_volume:'world_volume'}
      ], device_canvas_state:{snap:{enabled:false,grid:false,components:true,canvas:false,gridStep:12.5,thresholdPx:3}}}, 'snap-restore');
      const restored = {
        enabled: document.getElementById('snapOn').checked,
        grid: document.getElementById('snapGrid').checked,
        components: document.getElementById('snapComponents').checked,
        canvas: document.getElementById('snapCanvas').checked,
        gridStep: document.getElementById('gridStep').value,
        gridOriginLat: document.getElementById('gridOriginLat')?.value,
        gridOriginDep: document.getElementById('gridOriginDep')?.value,
        thresholdPx: document.getElementById('snapPx').value,
      };

      return {
        hasCompToggle, hasGridToggle, hasCanvasToggle, hasOriginLat, hasOriginDep, hasSettings,
        afterComponentSnap, afterComponentDisabled, afterGridSnap,
        exported, restored,
      };
    }"""
    )

    assert values["hasCompToggle"], values
    assert values["hasGridToggle"], values
    assert values["hasCanvasToggle"], values
    assert values["hasOriginLat"], values
    assert values["hasOriginDep"], values
    assert values["hasSettings"], values
    assert abs(values["afterComponentSnap"][0] - 20) < 1e-9, values
    assert abs(values["afterComponentDisabled"][0] - 31) < 1e-9, values
    assert abs(values["afterGridSnap"][0] - 30) < 1e-9, values
    assert values["exported"] == {
        "enabled": True,
        "grid": True,
        "components": False,
        "canvas": True,
        "gridStep": 25,
        "gridOriginLat": 5,
        "gridOriginDep": -10,
        "thresholdPx": 50,
    }, values
    assert values["restored"] == {
        "enabled": False,
        "grid": False,
        "components": True,
        "canvas": False,
        "gridStep": "12.5",
        "gridOriginLat": "0",
        "gridOriginDep": "0",
        "thresholdPx": "3",
    }, values
    print(values)


if __name__ == "__main__":
    main()
