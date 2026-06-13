from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:200,dy:200,dz:120}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'sensor', display_name:'Sensor', component_type:'layer', geometry_type:'box', dimensions:{dx:40,dy:30,dz:10}, material_id:'Silicon', placement:{position:[10,-20,0]}, mother_volume:'world_volume'}
      ]}, 'cad-status-bar');
      setViewAxes('x','z');
      const hud = document.getElementById('hudCoord');
      const initial = hud.textContent;

      const p = {x:X(25), y:Y(5)};
      const rect = stage.container().getBoundingClientRect();
      const evt = {clientX:rect.left + p.x, clientY:rect.top + p.y};
      stage.setPointersPositions(evt);
      stage.fire('mousemove', {target:stage, evt});
      const afterMove = hud.textContent;

      document.getElementById('snapOn').checked = false;
      onSnapSettingsChange();
      const afterSnapOff = hud.textContent;

      selectOnly('sensor');
      const afterSelect = hud.textContent;

      document.getElementById('sliceEnabled').checked = true;
      document.getElementById('slicePos').value = '-12';
      document.getElementById('sliceThickness').value = '4';
      onSliceSettingsChange();
      const afterSlice = hud.textContent;

      stage.fire('mouseleave', {target:stage, evt:{}});
      const afterLeave = hud.textContent;

      return {initial, afterMove, afterSnapOff, afterSelect, afterSlice, afterLeave};
    }"""
    )

    assert "cursor: --" in values["initial"], values
    assert "axis x/z" in values["initial"], values
    assert "third y" in values["initial"], values
    assert "snap on" in values["initial"], values
    assert "grid 100" in values["initial"], values
    assert "sel 0" in values["initial"], values
    assert "x 25" in values["afterMove"], values
    assert "z 5" in values["afterMove"], values
    assert "snap off" in values["afterSnapOff"], values
    assert "sel 1" in values["afterSelect"], values
    assert "slice y -12" in values["afterSlice"], values
    assert "±2.0" in values["afterSlice"], values
    assert "cursor: --" in values["afterLeave"], values
    assert "sel 1" in values["afterLeave"], values
    print(values)


if __name__ == "__main__":
    main()
