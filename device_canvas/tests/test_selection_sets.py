from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:400,dy:400,dz:160}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'a', display_name:'Layer A', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:80,dz:20}, material_id:'Silicon', placement:{position:[-80,0,0]}, mother_volume:'world_volume'},
        {component_id:'b', display_name:'Layer B', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:80,dz:20}, material_id:'SiO2', placement:{position:[0,0,0]}, mother_volume:'world_volume'},
        {component_id:'c', display_name:'Layer C', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:80,dz:20}, material_id:'Aluminum', placement:{position:[80,0,0]}, mother_volume:'world_volume'}
      ]}, 'selection-sets');
      selectedIds = new Set(['a','c']);
      primaryId = 'a';
      renderList();
      drawComponents();

      const hasFns = {
        save: typeof saveSelectionSet === 'function',
        apply: typeof applySelectionSet === 'function',
        isolate: typeof isolateSelectionSet === 'function',
        remove: typeof deleteSelectionSet === 'function',
        render: typeof renderSelectionSets === 'function',
      };
      const hasUi = {
        panel: !!document.getElementById('selectionSetList'),
        saveBtn: !!document.querySelector('[data-action="save-selection-set"]'),
      };
      const currentSets = () => typeof selectionSets === 'undefined' ? [] : selectionSets;

      if (hasFns.save) saveSelectionSet('Contacts');
      const afterSave = {
        sets: JSON.parse(JSON.stringify(currentSets())),
        panelText: document.getElementById('selectionSetList')?.textContent || '',
      };

      clearSelection();
      if (hasFns.apply && currentSets()[0]) applySelectionSet(currentSets()[0].id);
      const afterApply = {
        selected: Array.from(selectedIds).sort(),
        primaryId,
        renderedSelected: Array.from(document.querySelectorAll('#compList li.sel')).map(li => li.dataset.cid).sort(),
      };

      model.components.find(c => c.component_id === 'b').hidden = true;
      if (hasFns.isolate && currentSets()[0]) isolateSelectionSet(currentSets()[0].id);
      const afterIsolate = {
        active: isolationState.active,
        hidden: Object.fromEntries(model.components.map(c => [c.component_id, !!c.hidden])),
        visible: visibleComponentIds().sort(),
        selected: Array.from(selectedIds).sort(),
      };

      const exported = buildDeviceCanvasState().selectionSets || [];
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:400,dy:400,dz:160}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'a', display_name:'Layer A', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:80,dz:20}, material_id:'Silicon', placement:{position:[-80,0,0]}, mother_volume:'world_volume'},
        {component_id:'b', display_name:'Layer B', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:80,dz:20}, material_id:'SiO2', placement:{position:[0,0,0]}, mother_volume:'world_volume'},
        {component_id:'c', display_name:'Layer C', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:80,dz:20}, material_id:'Aluminum', placement:{position:[80,0,0]}, mother_volume:'world_volume'}
      ], device_canvas_state:{selectionSets: exported}}, 'selection-sets-restored');
      const afterRestore = {
        sets: JSON.parse(JSON.stringify(currentSets())),
        panelText: document.getElementById('selectionSetList')?.textContent || '',
      };

      if (hasFns.remove && currentSets()[0]) deleteSelectionSet(currentSets()[0].id);
      const afterDelete = {
        count: currentSets().length,
        panelText: document.getElementById('selectionSetList')?.textContent || '',
      };

      return {hasFns, hasUi, afterSave, afterApply, afterIsolate, exported, afterRestore, afterDelete, historyPtr: history.ptr};
    }"""
    )

    assert all(values["hasFns"].values()), values
    assert all(values["hasUi"].values()), values
    assert values["afterSave"]["sets"][0]["name"] == "Contacts", values
    assert values["afterSave"]["sets"][0]["componentIds"] == ["a", "c"], values
    assert "Contacts" in values["afterSave"]["panelText"], values

    assert values["afterApply"]["selected"] == ["a", "c"], values
    assert values["afterApply"]["primaryId"] == "a", values
    assert values["afterApply"]["renderedSelected"] == ["a", "c"], values

    assert values["afterIsolate"]["active"] is True, values
    assert values["afterIsolate"]["hidden"] == {
        "world_volume": False,
        "a": False,
        "b": True,
        "c": False,
    }, values
    assert values["afterIsolate"]["visible"] == ["a", "c", "world_volume"], values
    assert values["afterIsolate"]["selected"] == ["a", "c"], values

    assert values["exported"][0]["name"] == "Contacts", values
    assert values["exported"][0]["componentIds"] == ["a", "c"], values
    assert values["afterRestore"]["sets"][0]["name"] == "Contacts", values
    assert "Contacts" in values["afterRestore"]["panelText"], values
    assert values["afterDelete"]["count"] == 0, values
    assert "无保存选区" in values["afterDelete"]["panelText"], values
    assert values["historyPtr"] >= 0, values
    print(values)


if __name__ == "__main__":
    main()
