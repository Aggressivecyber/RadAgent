from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """async () => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:260,dy:260,dz:160}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'sensor_a', display_name:'Sensor A', component_type:'layer', geometry_type:'box', dimensions:{dx:30,dy:30,dz:10}, material_id:'Silicon', placement:{position:[-60,0,0]}, mother_volume:'world_volume'},
        {component_id:'sensor_b', display_name:'Sensor B', component_type:'layer', geometry_type:'box', dimensions:{dx:30,dy:30,dz:10}, material_id:'Silicon', placement:{position:[0,0,0]}, mother_volume:'world_volume', hidden:true},
        {component_id:'guard_locked', display_name:'Guard Locked', component_type:'electrode', geometry_type:'box', dimensions:{dx:20,dy:20,dz:6}, material_id:'Aluminum', placement:{position:[60,0,0]}, mother_volume:'world_volume', locked:true},
        {component_id:'poly', display_name:'Editable Poly', component_type:'layer', geometry_type:'polycone', dimensions:{dx:20,dy:20,dz:10}, material_id:'SiO2', placement:{position:[0,60,0]}, mother_volume:'world_volume',
          cross_section_polygon:[[-10,50,0],[10,50,0],[10,70,0],[-10,70,0]], cross_section_polygon_axes:{lateral:'x',depth:'y'}}
      ]}, 'keyboard-shortcuts');
      setViewAxes('x','y');

      const fireKey = async (key, opts = {}) => {
        const ev = new KeyboardEvent('keydown', {key, bubbles:true, cancelable:true, ...opts});
        const prevented = !window.dispatchEvent(ev);
        await new Promise(resolve => setTimeout(resolve, 0));
        return prevented;
      };

      document.getElementById('componentSearch').value = 'sensor';
      document.getElementById('componentStatusFilter').value = 'visible';
      onComponentListFilterChange();
      const ctrlA = await fireKey('a', {ctrlKey:true});
      const afterCtrlA = {
        prevented: ctrlA,
        selected: [...selectedIds].sort(),
        primaryId,
      };

      selectOnly('poly');
      selectPolygonVertex(2);
      measureState = {start:{lat:0,dep:0}, end:{lat:10,dep:10}, preview:null};
      drawMeasurement();
      const beforeEscape = {
        selected: [...selectedIds],
        polyEditId,
        vertex: selectedPolygonVertexIndex,
        measurementNodes: measureGroup.children.length,
      };
      const escape = await fireKey('Escape');
      const afterEscape = {
        prevented: escape,
        selected: [...selectedIds],
        primaryId,
        polyEditId,
        vertex: selectedPolygonVertexIndex,
        measurementNodes: measureGroup.children.length,
      };

      const input = document.getElementById('componentSearch');
      input.focus();
      input.value = 'locked';
      const typingCtrlA = await fireKey('a', {ctrlKey:true});
      const afterTypingCtrlA = {
        prevented: typingCtrlA,
        selected: [...selectedIds],
        search: input.value,
      };

      return {afterCtrlA, beforeEscape, afterEscape, afterTypingCtrlA};
    }"""
    )

    assert values["afterCtrlA"] == {
        "prevented": True,
        "selected": ["sensor_a"],
        "primaryId": "sensor_a",
    }, values
    assert values["beforeEscape"]["selected"] == ["poly"], values
    assert values["beforeEscape"]["polyEditId"] == "poly", values
    assert values["beforeEscape"]["vertex"] == 2, values
    assert values["beforeEscape"]["measurementNodes"] > 0, values
    assert values["afterEscape"] == {
        "prevented": True,
        "selected": [],
        "primaryId": None,
        "polyEditId": None,
        "vertex": None,
        "measurementNodes": 0,
    }, values
    assert values["afterTypingCtrlA"] == {
        "prevented": False,
        "selected": [],
        "search": "locked",
    }, values
    print(values)


if __name__ == "__main__":
    main()
