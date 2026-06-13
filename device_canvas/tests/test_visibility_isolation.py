from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:400,dy:400,dz:160}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'a', display_name:'Layer A', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:80,dz:20}, material_id:'Silicon', placement:{position:[-80,0,0]}, mother_volume:'world_volume'},
        {component_id:'b', display_name:'Layer B', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:80,dz:20}, material_id:'SiO2', placement:{position:[0,0,0]}, mother_volume:'world_volume'},
        {component_id:'c', display_name:'Layer C', component_type:'layer', geometry_type:'box', dimensions:{dx:80,dy:80,dz:20}, material_id:'Aluminum', placement:{position:[80,0,0]}, mother_volume:'world_volume'}
      ]}, 'visibility-isolation');
      model.components.find(c => c.component_id === 'b').hidden = true;
      selectedIds = new Set(['a','c']);
      primaryId = 'a';
      renderList();
      drawComponents();

      const hasFns = {
        isolate: typeof isolateSelection === 'function',
        restore: typeof restoreIsolation === 'function',
        showAll: typeof showAllComponents === 'function',
        isolateBtn: !!document.querySelector('[data-action="isolate-selection"]'),
        restoreBtn: !!document.querySelector('[data-action="restore-isolation"]'),
        showAllBtn: !!document.querySelector('[data-action="show-all-components"]'),
      };

      isolateSelection();
      const afterIsolate = {
        active: isolationState.active,
        hidden: Object.fromEntries(model.components.map(c => [c.component_id, !!c.hidden])),
        visibleIds: visibleComponentIds().sort(),
        renderedIds: Array.from(rectNodes.keys()).sort(),
        selected: Array.from(selectedIds).sort(),
      };

      selectedIds = new Set(['c']);
      primaryId = 'c';
      isolateSelection();
      const afterSecondIsolate = {
        active: isolationState.active,
        hidden: Object.fromEntries(model.components.map(c => [c.component_id, !!c.hidden])),
      };

      restoreIsolation();
      const afterRestore = {
        active: isolationState.active,
        hidden: Object.fromEntries(model.components.map(c => [c.component_id, !!c.hidden])),
        visibleIds: visibleComponentIds().sort(),
        selected: Array.from(selectedIds).sort(),
      };

      showAllComponents();
      const afterShowAll = {
        active: isolationState.active,
        hidden: Object.fromEntries(model.components.map(c => [c.component_id, !!c.hidden])),
        visibleIds: visibleComponentIds().sort(),
      };

      return {hasFns, afterIsolate, afterSecondIsolate, afterRestore, afterShowAll, historyPtr: history.ptr};
    }"""
    )

    assert all(values["hasFns"].values()), values
    assert values["afterIsolate"]["active"] is True, values
    assert values["afterIsolate"]["hidden"] == {
        "world_volume": False,
        "a": False,
        "b": True,
        "c": False,
    }, values
    assert values["afterIsolate"]["visibleIds"] == ["a", "c", "world_volume"], values
    assert values["afterIsolate"]["renderedIds"] == ["a", "c", "world_volume"], values
    assert values["afterIsolate"]["selected"] == ["a", "c"], values

    assert values["afterSecondIsolate"]["active"] is True, values
    assert values["afterSecondIsolate"]["hidden"] == {
        "world_volume": False,
        "a": True,
        "b": True,
        "c": False,
    }, values

    assert values["afterRestore"]["active"] is False, values
    assert values["afterRestore"]["hidden"] == {
        "world_volume": False,
        "a": False,
        "b": True,
        "c": False,
    }, values
    assert values["afterRestore"]["visibleIds"] == ["a", "c", "world_volume"], values
    assert values["afterRestore"]["selected"] == ["c"], values

    assert values["afterShowAll"]["active"] is False, values
    assert values["afterShowAll"]["hidden"] == {
        "world_volume": False,
        "a": False,
        "b": False,
        "c": False,
    }, values
    assert values["afterShowAll"]["visibleIds"] == ["a", "b", "c", "world_volume"], values
    assert values["historyPtr"] >= 3, values
    print(values)


if __name__ == "__main__":
    main()
