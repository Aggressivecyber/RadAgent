from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({
        components:[
          {component_id:'world_volume',display_name:'World',component_type:'world',geometry_type:'box',dimensions:{dx:400,dy:400,dz:400},material_id:'Air',placement:{position:[0,0,0]}},
          {component_id:'si_bulk',display_name:'Si Bulk',component_type:'substrate',geometry_type:'box',dimensions:{dx:120,dy:100,dz:40},material_id:'Silicon',placement:{position:[0,0,0]},mother_volume:'world_volume'},
          {component_id:'si_window',display_name:'Si Window',component_type:'layer',geometry_type:'box',dimensions:{dx:120,dy:100,dz:5},material_id:'Silicon',placement:{position:[0,0,30]},mother_volume:'world_volume'},
          {component_id:'al_top',display_name:'Al Top',component_type:'electrode',geometry_type:'box',dimensions:{dx:100,dy:80,dz:4},material_id:'Aluminum',placement:{position:[0,0,36]},mother_volume:'world_volume'},
          {component_id:'al_back',display_name:'Al Back',component_type:'electrode',geometry_type:'box',dimensions:{dx:100,dy:80,dz:4},material_id:'Aluminum',placement:{position:[0,0,-36]},mother_volume:'world_volume',hidden:true},
        ]
      });

      const hasFns = {
        rows: typeof layerGroupRows === 'function',
        render: typeof renderLayerGroups === 'function',
        select: typeof selectLayerGroup === 'function',
        isolate: typeof isolateLayerGroup === 'function',
        hidden: typeof setLayerGroupHidden === 'function',
        locked: typeof setLayerGroupLocked === 'function',
      };
      const hasUi = {
        mode: !!document.getElementById('layerGroupMode'),
        list: !!document.getElementById('layerGroupList'),
      };

      const materialRows = layerGroupRows('material').map(r => ({
        key:r.key,
        count:r.count,
        visibleCount:r.visibleCount,
        lockedCount:r.lockedCount,
        ids:r.componentIds,
      }));
      const panelText = document.getElementById('layerGroupList').textContent;

      selectLayerGroup('material', 'Silicon');
      const afterSelectSilicon = {
        selected:[...selectedIds].sort(),
        primaryId,
      };

      isolateLayerGroup('material', 'Silicon');
      const afterIsolateSilicon = {
        active:isolationState.active,
        selected:[...selectedIds].sort(),
        hidden:Object.fromEntries(model.components.map(c => [c.component_id, !!c.hidden])),
        visible:visibleComponentIds().sort(),
      };

      showAllComponents();
      setLayerGroupHidden('type', 'electrode', true);
      const afterHideElectrodes = {
        hidden:Object.fromEntries(model.components.map(c => [c.component_id, !!c.hidden])),
        visible:visibleComponentIds().sort(),
      };

      setLayerGroupHidden('type', 'electrode', false);
      setLayerGroupLocked('material', 'Aluminum', true);
      const afterLockAluminum = {
        locked:Object.fromEntries(model.components.map(c => [c.component_id, !!c.locked])),
        rows:layerGroupRows('material').filter(r => r.key === 'Aluminum').map(r => ({lockedCount:r.lockedCount, count:r.count})),
      };

      document.getElementById('layerGroupMode').value = 'type';
      onLayerGroupModeChange();
      const typePanelText = document.getElementById('layerGroupList').textContent;
      const typeRows = layerGroupRows('type').map(r => ({key:r.key, count:r.count, ids:r.componentIds}));

      return {hasFns, hasUi, materialRows, panelText, afterSelectSilicon, afterIsolateSilicon, afterHideElectrodes, afterLockAluminum, typePanelText, typeRows};
    }"""
    )

    assert all(values["hasFns"].values()), values
    assert all(values["hasUi"].values()), values
    silicon = next(row for row in values["materialRows"] if row["key"] == "Silicon")
    aluminum = next(row for row in values["materialRows"] if row["key"] == "Aluminum")
    assert silicon["count"] == 2 and silicon["visibleCount"] == 2, values
    assert aluminum["count"] == 2 and aluminum["visibleCount"] == 1, values
    assert "Silicon" in values["panelText"] and "Aluminum" in values["panelText"], values
    assert values["afterSelectSilicon"]["selected"] == ["si_bulk", "si_window"], values
    assert values["afterSelectSilicon"]["primaryId"] == "si_bulk", values
    assert values["afterIsolateSilicon"]["active"], values
    assert values["afterIsolateSilicon"]["hidden"]["world_volume"] is False, values
    assert values["afterIsolateSilicon"]["hidden"]["al_top"] is True, values
    assert values["afterIsolateSilicon"]["hidden"]["al_back"] is True, values
    assert values["afterIsolateSilicon"]["visible"] == ["si_bulk", "si_window", "world_volume"], values
    assert values["afterHideElectrodes"]["hidden"]["al_top"] is True, values
    assert values["afterHideElectrodes"]["hidden"]["al_back"] is True, values
    assert values["afterHideElectrodes"]["visible"] == ["si_bulk", "si_window", "world_volume"], values
    assert values["afterLockAluminum"]["locked"]["al_top"] is True, values
    assert values["afterLockAluminum"]["locked"]["al_back"] is True, values
    assert values["afterLockAluminum"]["locked"]["world_volume"] is False, values
    assert values["afterLockAluminum"]["rows"] == [{"lockedCount": 2, "count": 2}], values
    assert "electrode" in values["typePanelText"], values
    electrode = next(row for row in values["typeRows"] if row["key"] == "electrode")
    assert electrode["count"] == 2 and electrode["ids"] == ["al_top", "al_back"], values
    print(values)


if __name__ == "__main__":
    main()
