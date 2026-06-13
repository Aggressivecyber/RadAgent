from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:600,dy:600,dz:300}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'module', display_name:'Detector Module', component_type:'assembly', geometry_type:'box', dimensions:{dx:260,dy:220,dz:120}, material_id:'Air', placement:{position:[0,0,0]}, mother_volume:'world_volume'},
        {component_id:'sensor_a', display_name:'Sensor A', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:80,dz:10}, material_id:'Silicon', placement:{position:[-40,0,10]}, mother_volume:'module'},
        {component_id:'sensor_b', display_name:'Sensor B', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:80,dz:10}, material_id:'Silicon', placement:{position:[40,0,10]}, mother_volume:'module'},
        {component_id:'shield', display_name:'Shield', component_type:'shield', geometry_type:'box', dimensions:{dx:320,dy:320,dz:20}, material_id:'Aluminum', placement:{position:[0,0,-80]}, mother_volume:'world_volume'}
      ]}, 'assembly-tree');

      const hasFns = {
        rows: typeof assemblyTreeRows === 'function',
        subtree: typeof assemblySubtreeIds === 'function',
        render: typeof renderAssemblyTree === 'function',
        select: typeof selectAssemblySubtree === 'function',
        isolate: typeof isolateAssemblySubtree === 'function',
        hide: typeof hideAssemblySubtree === 'function',
      };
      const hasUi = {
        panel: !!document.getElementById('assemblyTreeList'),
      };
      const safeRows = hasFns.rows ? assemblyTreeRows() : [];
      const safeSubtree = id => hasFns.subtree ? assemblySubtreeIds(id) : [];

      if (hasFns.render) renderAssemblyTree();
      const afterRender = {
        rows: safeRows.map(r => ({id: r.component.component_id, depth: r.depth, childCount: r.childCount, subtreeCount: r.subtreeIds.length})),
        panelText: document.getElementById('assemblyTreeList')?.textContent || '',
        rowIds: Array.from(document.querySelectorAll('#assemblyTreeList [data-cid]')).map(x => x.dataset.cid),
        moduleSubtree: safeSubtree('module'),
        worldSubtree: safeSubtree('world_volume'),
      };

      if (hasFns.select) selectAssemblySubtree('module');
      const afterSelect = {
        selected: Array.from(selectedIds).sort(),
        primaryId,
        renderedSelected: Array.from(document.querySelectorAll('#compList li.sel')).map(li => li.dataset.cid).sort(),
      };

      if (hasFns.isolate) isolateAssemblySubtree('module');
      const afterIsolate = {
        active: isolationState.active,
        selected: Array.from(selectedIds).sort(),
        hidden: Object.fromEntries(model.components.map(c => [c.component_id, !!c.hidden])),
        visible: visibleComponentIds().sort(),
      };

      restoreIsolation();
      if (hasFns.hide) hideAssemblySubtree('module', true);
      const afterHide = {
        hidden: Object.fromEntries(model.components.map(c => [c.component_id, !!c.hidden])),
        selected: Array.from(selectedIds).sort(),
      };
      if (hasFns.hide) hideAssemblySubtree('module', false);
      const afterShow = {
        hidden: Object.fromEntries(model.components.map(c => [c.component_id, !!c.hidden])),
        visible: visibleComponentIds().sort(),
      };

      return {hasFns, hasUi, afterRender, afterSelect, afterIsolate, afterHide, afterShow};
    }"""
    )

    assert all(values["hasFns"].values()), values
    assert all(values["hasUi"].values()), values
    assert values["afterRender"]["moduleSubtree"] == ["module", "sensor_a", "sensor_b"], values
    assert values["afterRender"]["worldSubtree"] == [
        "module",
        "sensor_a",
        "sensor_b",
        "shield",
    ], values
    assert {"id": "module", "depth": 1, "childCount": 2, "subtreeCount": 3} in values["afterRender"]["rows"], values
    assert "Detector Module" in values["afterRender"]["panelText"], values
    assert values["afterRender"]["rowIds"] == [
        "world_volume",
        "module",
        "sensor_a",
        "sensor_b",
        "shield",
    ], values

    assert values["afterSelect"]["selected"] == ["module", "sensor_a", "sensor_b"], values
    assert values["afterSelect"]["primaryId"] == "module", values
    assert values["afterSelect"]["renderedSelected"] == ["module", "sensor_a", "sensor_b"], values

    assert values["afterIsolate"]["active"] is True, values
    assert values["afterIsolate"]["selected"] == ["module", "sensor_a", "sensor_b"], values
    assert values["afterIsolate"]["hidden"] == {
        "world_volume": False,
        "module": False,
        "sensor_a": False,
        "sensor_b": False,
        "shield": True,
    }, values
    assert values["afterIsolate"]["visible"] == [
        "module",
        "sensor_a",
        "sensor_b",
        "world_volume",
    ], values

    assert values["afterHide"]["hidden"] == {
        "world_volume": False,
        "module": True,
        "sensor_a": True,
        "sensor_b": True,
        "shield": False,
    }, values
    assert values["afterHide"]["selected"] == [], values
    assert values["afterShow"]["hidden"] == {
        "world_volume": False,
        "module": False,
        "sensor_a": False,
        "sensor_b": False,
        "shield": False,
    }, values
    assert values["afterShow"]["visible"] == [
        "module",
        "sensor_a",
        "sensor_b",
        "shield",
        "world_volume",
    ], values
    print(values)


if __name__ == "__main__":
    main()
