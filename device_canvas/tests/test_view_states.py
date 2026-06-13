from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:400,dy:400,dz:160}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'a', display_name:'Layer A', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:80,dz:20}, material_id:'Silicon', placement:{position:[-80,0,0]}, mother_volume:'world_volume'},
        {component_id:'b', display_name:'Layer B', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:80,dz:20}, material_id:'SiO2', placement:{position:[0,0,0]}, mother_volume:'world_volume'},
        {component_id:'c', display_name:'Layer C', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:80,dz:20}, material_id:'Aluminum', placement:{position:[80,0,0]}, mother_volume:'world_volume'}
      ]}, 'view-states');
      setViewAxes('x','y');
      model.components.find(c => c.component_id === 'b').hidden = true;
      model.components.find(c => c.component_id === 'c').locked = true;
      sliceState = {enabled:true, pos:12, thickness:4};
      updateSliceUI();
      refreshVisibilityViews(false);

      const hasFns = {
        save: typeof saveViewState === 'function',
        apply: typeof applyViewState === 'function',
        remove: typeof deleteViewState === 'function',
        render: typeof renderViewStates === 'function',
      };
      const hasUi = {
        panel: !!document.getElementById('viewStateList'),
        saveBtn: !!document.querySelector('[data-action="save-view-state"]'),
      };
      const currentStates = () => typeof viewStates === 'undefined' ? [] : viewStates;
      if (!hasFns.save || !hasFns.apply || !hasFns.remove || !hasFns.render || !hasUi.panel || !hasUi.saveBtn) {
        return {hasFns, hasUi};
      }

      const saved = saveViewState('Review Slice');
      const afterSave = {
        states: JSON.parse(JSON.stringify(currentStates())),
        panelText: document.getElementById('viewStateList')?.textContent || '',
      };

      setViewAxes('y','z');
      model.components.forEach(c => { c.hidden = false; if (!isWorld(c)) c.locked = false; });
      sliceState = {enabled:false, pos:0, thickness:1};
      updateSliceUI();
      refreshVisibilityViews(false);

      applyViewState(saved.id);
      const afterApply = {
        axes: {...axes},
        slice: {...sliceState},
        hidden: Object.fromEntries(model.components.map(c => [c.component_id, !!c.hidden])),
        locked: Object.fromEntries(model.components.map(c => [c.component_id, !!c.locked])),
        visible: visibleComponentIds().sort(),
        panelText: document.getElementById('viewStateList')?.textContent || '',
      };

      const exported = buildDeviceCanvasState().viewStates || [];
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:400,dy:400,dz:160}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'a', display_name:'Layer A', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:80,dz:20}, material_id:'Silicon', placement:{position:[-80,0,0]}, mother_volume:'world_volume'},
        {component_id:'b', display_name:'Layer B', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:80,dz:20}, material_id:'SiO2', placement:{position:[0,0,0]}, mother_volume:'world_volume'},
        {component_id:'c', display_name:'Layer C', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:80,dz:20}, material_id:'Aluminum', placement:{position:[80,0,0]}, mother_volume:'world_volume'}
      ], device_canvas_state:{viewStates: exported}}, 'view-states-restored');
      const afterRestore = {
        states: JSON.parse(JSON.stringify(currentStates())),
        panelText: document.getElementById('viewStateList')?.textContent || '',
      };
      applyViewState(afterRestore.states[0].id);
      const afterRestoreApply = {
        axes: {...axes},
        slice: {...sliceState},
        hidden: Object.fromEntries(model.components.map(c => [c.component_id, !!c.hidden])),
        locked: Object.fromEntries(model.components.map(c => [c.component_id, !!c.locked])),
      };

      deleteViewState(afterRestore.states[0].id);
      const afterDelete = {
        count: currentStates().length,
        panelText: document.getElementById('viewStateList')?.textContent || '',
      };

      return {hasFns, hasUi, afterSave, afterApply, exported, afterRestore, afterRestoreApply, afterDelete};
    }"""
    )

    assert values["hasFns"] == {
        "save": True,
        "apply": True,
        "remove": True,
        "render": True,
    }, values
    assert values["hasUi"] == {
        "panel": True,
        "saveBtn": True,
    }, values
    assert values["afterSave"]["states"][0]["name"] == "Review Slice", values
    assert values["afterSave"]["states"][0]["axes"] == {"lateral": "x", "depth": "y"}, values
    assert values["afterSave"]["states"][0]["slice"] == {
        "enabled": True,
        "pos": 12,
        "thickness": 4,
    }, values
    assert values["afterSave"]["states"][0]["layers"]["b"]["hidden"] is True, values
    assert values["afterSave"]["states"][0]["layers"]["c"]["locked"] is True, values
    assert "Review Slice" in values["afterSave"]["panelText"], values

    assert values["afterApply"]["axes"] == {"lateral": "x", "depth": "y"}, values
    assert values["afterApply"]["slice"] == {"enabled": True, "pos": 12, "thickness": 4}, values
    assert values["afterApply"]["hidden"] == {
        "world_volume": False,
        "a": False,
        "b": True,
        "c": False,
    }, values
    assert values["afterApply"]["locked"]["c"] is True, values
    assert values["afterApply"]["visible"] == ["a", "c", "world_volume"], values

    assert values["exported"][0]["name"] == "Review Slice", values
    assert values["afterRestore"]["states"][0]["name"] == "Review Slice", values
    assert "Review Slice" in values["afterRestore"]["panelText"], values
    assert values["afterRestoreApply"]["axes"] == {"lateral": "x", "depth": "y"}, values
    assert values["afterRestoreApply"]["slice"] == {"enabled": True, "pos": 12, "thickness": 4}, values
    assert values["afterRestoreApply"]["hidden"]["b"] is True, values
    assert values["afterRestoreApply"]["locked"]["c"] is True, values
    assert values["afterDelete"]["count"] == 0, values
    assert "无保存视图" in values["afterDelete"]["panelText"], values
    print(values)


if __name__ == "__main__":
    main()
