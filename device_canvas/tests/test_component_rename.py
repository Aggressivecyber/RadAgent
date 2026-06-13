from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:300,dy:300,dz:160}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'module_a', display_name:'Module A', component_type:'assembly', geometry_type:'box', dimensions:{dx:140,dy:120,dz:80}, material_id:'Air', placement:{position:[0,0,0]}, mother_volume:'world_volume'},
        {component_id:'sensor_old', display_name:'Sensor Old', component_type:'layer', geometry_type:'box', dimensions:{dx:40,dy:30,dz:10}, material_id:'Silicon', placement:{position:[-40,0,0]}, mother_volume:'module_a'},
        {component_id:'guard', display_name:'Guard', component_type:'electrode', geometry_type:'box', dimensions:{dx:30,dy:30,dz:10}, material_id:'Aluminum', placement:{position:[20,0,0]}, mother_volume:'sensor_old'}
      ]}, 'component-rename');
      setViewAxes('x','z');
      selectedIds = new Set(['sensor_old']);
      primaryId = 'sensor_old';
      saveSelectionSet('Sensor Set');
      createDimensionsForSelection();
      selectedIds = new Set(['sensor_old', 'guard']);
      primaryId = 'sensor_old';
      createPairGapAnnotation();
      drcWaivers = [{
        signature:'overlap3d:guard+sensor_old',
        code:'overlap3d',
        ids:['guard','sensor_old'],
        reason:'known fixture',
        waivedAt:'2026-06-13T00:00:00.000Z'
      }];
      selectOnly('sensor_old');
      const historyBefore = history.ptr;

      const hasFn = typeof renameComponent === 'function';
      const result = renameComponent('sensor_old', {component_id:'sensor_main', display_name:'Main Sensor'});
      const renamed = model.components.find(c => c.component_id === 'sensor_main');
      const oldExists = !!model.components.find(c => c.component_id === 'sensor_old');
      const guard = model.components.find(c => c.component_id === 'guard');
      const selectionSet = selectionSets[0];
      const annotations = dimensionAnnotations.map(a => ({
        id:a.id,
        kind:a.kind,
        component_id:a.component_id,
        a_id:a.a_id,
        b_id:a.b_id,
      }));
      const waiver = drcWaivers[0];
      const listText = document.getElementById('compList').textContent;

      selectOnly('sensor_main');
      const idInput = document.getElementById('f_id');
      idInput.value = 'guard';
      idInput.dispatchEvent(new Event('change', {bubbles:true}));
      const duplicateAttempt = {
        ok: model.components.some(c => c.component_id === 'guard') && model.components.some(c => c.component_id === 'sensor_main'),
        input: document.getElementById('f_id').value,
        primaryId,
      };

      const invalidInput = document.getElementById('f_id');
      invalidInput.value = 'bad id with spaces';
      invalidInput.dispatchEvent(new Event('change', {bubbles:true}));
      const invalidAttempt = {
        exists: !!model.components.find(c => c.component_id === 'bad id with spaces'),
        input: document.getElementById('f_id').value,
        primaryId,
      };

      const exported = serializeComp(renamed);
      return {
        hasFn,
        result,
        renamed:{id:renamed.component_id, name:renamed.display_name},
        oldExists,
        guardMother:guard.mother_volume,
        selected:[...selectedIds],
        primaryId,
        selectionSet,
        annotations,
        waiver,
        listText,
        duplicateAttempt,
        invalidAttempt,
        exported,
        historyBefore,
        historyAfter: history.ptr,
      };
    }"""
    )

    assert values["hasFn"] is True, values
    assert values["result"]["ok"] is True, values
    assert values["renamed"] == {"id": "sensor_main", "name": "Main Sensor"}, values
    assert values["oldExists"] is False, values
    assert values["guardMother"] == "sensor_main", values
    assert values["selected"] == ["sensor_main"], values
    assert values["primaryId"] == "sensor_main", values
    assert values["selectionSet"]["componentIds"] == ["sensor_main"], values
    component_ann = next(a for a in values["annotations"] if a["kind"] == "component_dimension")
    pair_ann = next(a for a in values["annotations"] if a["kind"] == "pair_gap")
    assert component_ann["component_id"] == "sensor_main", values
    assert pair_ann["a_id"] == "sensor_main" and pair_ann["b_id"] == "guard", values
    assert pair_ann["id"] == "pair_gap:sensor_main:guard:x", values
    assert values["waiver"]["signature"] == "overlap3d:guard+sensor_main", values
    assert values["waiver"]["ids"] == ["guard", "sensor_main"], values
    assert "Main Sensor" in values["listText"] and "sensor_main" in values["listText"], values
    assert values["duplicateAttempt"] == {
        "ok": True,
        "input": "sensor_main",
        "primaryId": "sensor_main",
    }, values
    assert values["invalidAttempt"] == {
        "exists": False,
        "input": "sensor_main",
        "primaryId": "sensor_main",
    }, values
    assert values["exported"]["component_id"] == "sensor_main", values
    assert values["historyAfter"] > values["historyBefore"], values
    print(values)


if __name__ == "__main__":
    main()
