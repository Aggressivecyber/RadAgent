from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:300,dy:300,dz:120}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'sensor_active', display_name:'Active Sensor', component_type:'layer', geometry_type:'box', dimensions:{dx:40,dy:40,dz:10}, material_id:'Silicon', placement:{position:[-60,0,0]}, mother_volume:'world_volume', roles:['edep_region']},
        {component_id:'oxide_hidden', display_name:'Hidden Oxide', component_type:'layer', geometry_type:'box', dimensions:{dx:30,dy:30,dz:6}, material_id:'SiO2', placement:{position:[0,0,0]}, mother_volume:'world_volume', hidden:true},
        {component_id:'guard_locked', display_name:'Locked Guard', component_type:'electrode', geometry_type:'box', dimensions:{dx:20,dy:20,dz:4}, material_id:'Aluminum', placement:{position:[60,0,0]}, mother_volume:'world_volume', locked:true, roles:['guard_ring']}
      ]}, 'component-list-filters');

      const rowIds = () => Array.from(document.querySelectorAll('#compList li[data-cid]')).map(li => li.dataset.cid);
      const setSearch = value => {
        const el = document.getElementById('componentSearch');
        el.value = value;
        renderList();
        return rowIds();
      };
      const setStatus = value => {
        const el = document.getElementById('componentStatusFilter');
        if (el) el.value = value;
        if (typeof onComponentListFilterChange === 'function') onComponentListFilterChange();
        return rowIds();
      };

      const hasUi = {
        search: !!document.getElementById('componentSearch'),
        status: !!document.getElementById('componentStatusFilter'),
        clear: !!document.querySelector('[data-action="clear-component-list-filter"]'),
      };
      const hasFns = {
        passes: typeof componentPassesListFilter === 'function',
        setStatus: typeof onComponentListFilterChange === 'function',
        clear: typeof clearComponentListFilter === 'function',
      };

      const initialRows = rowIds();
      const materialSearch = setSearch('sio2');
      const roleSearch = setSearch('guard_ring');
      const idSearch = setSearch('sensor_active');

      setSearch('');
      const visibleRows = setStatus('visible');
      const visibleIds = visibleComponentIds().sort();
      const hiddenRows = setStatus('hidden');
      const lockedRows = setStatus('locked');

      document.getElementById('componentSearch').value = 'guard';
      onComponentListFilterChange();
      const lockedSearchRows = rowIds();
      clearComponentListFilter();
      const afterClear = {
        search: document.getElementById('componentSearch').value,
        status: document.getElementById('componentStatusFilter').value,
        rows: rowIds(),
      };

      return {hasUi, hasFns, initialRows, materialSearch, roleSearch, idSearch, visibleRows, visibleIds, hiddenRows, lockedRows, lockedSearchRows, afterClear};
    }"""
    )

    assert all(values["hasUi"].values()), values
    assert all(values["hasFns"].values()), values
    assert values["initialRows"] == ["world_volume", "sensor_active", "oxide_hidden", "guard_locked"], values
    assert values["materialSearch"] == ["oxide_hidden"], values
    assert values["roleSearch"] == ["guard_locked"], values
    assert values["idSearch"] == ["sensor_active"], values
    assert values["visibleRows"] == ["world_volume", "sensor_active", "guard_locked"], values
    assert values["visibleIds"] == ["guard_locked", "sensor_active", "world_volume"], values
    assert values["hiddenRows"] == ["oxide_hidden"], values
    assert values["lockedRows"] == ["guard_locked"], values
    assert values["lockedSearchRows"] == ["guard_locked"], values
    assert values["afterClear"] == {
        "search": "",
        "status": "all",
        "rows": ["world_volume", "sensor_active", "oxide_hidden", "guard_locked"],
    }, values
    print(values)


if __name__ == "__main__":
    main()
