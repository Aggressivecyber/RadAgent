from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """async () => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:260,dy:260,dz:160}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'sensor_a', display_name:'Sensor A', component_type:'layer', geometry_type:'box', dimensions:{dx:30,dy:30,dz:10}, material_id:'Silicon', placement:{position:[-60,0,0]}, mother_volume:'world_volume'},
        {component_id:'sensor_b', display_name:'Sensor B', component_type:'layer', geometry_type:'box', dimensions:{dx:30,dy:30,dz:10}, material_id:'Silicon', placement:{position:[0,0,0]}, mother_volume:'world_volume', hidden:true},
        {component_id:'guard', display_name:'Guard Ring', component_type:'electrode', geometry_type:'box', dimensions:{dx:20,dy:20,dz:6}, material_id:'Aluminum', placement:{position:[60,0,0]}, mother_volume:'world_volume'}
      ]}, 'command-palette');

      const fireKey = async (key, opts = {}) => {
        const ev = new KeyboardEvent('keydown', {key, bubbles:true, cancelable:true, ...opts});
        const prevented = !window.dispatchEvent(ev);
        await new Promise(resolve => setTimeout(resolve, 0));
        return prevented;
      };
      const visibleCommandIds = () => [...document.querySelectorAll('[data-command-id]')]
        .filter(el => !el.disabled)
        .map(el => el.dataset.commandId);

      const hasApi = {
        commands: Array.isArray(window.CAD_COMMANDS),
        open: typeof openCommandPalette === 'function',
        close: typeof closeCommandPalette === 'function',
        run: typeof runCadCommand === 'function',
      };
      const hasUi = {
        button: !!document.querySelector('[data-action="open-command-palette"]'),
        panel: !!document.getElementById('commandPalette'),
        search: !!document.getElementById('commandPaletteSearch'),
        list: !!document.getElementById('commandPaletteList'),
      };
      if (!hasApi.open || !hasUi.panel || !hasUi.search || !hasUi.list) {
        return {hasApi, hasUi};
      }

      const ctrlK = await fireKey('k', {ctrlKey:true});
      const afterOpen = {
        prevented: ctrlK,
        hidden: document.getElementById('commandPalette')?.hidden,
        focused: document.activeElement?.id,
        resultCount: document.querySelectorAll('[data-command-id]').length,
      };

      const search = document.getElementById('commandPaletteSearch');
      search.value = '全部';
      search.dispatchEvent(new Event('input', {bubbles:true}));
      const searchIds = visibleCommandIds();
      const enterSelectAll = await fireKey('Enter');
      const afterSelectAll = {
        prevented: enterSelectAll,
        hidden: document.getElementById('commandPalette')?.hidden,
        selected: [...selectedIds].sort(),
        primaryId,
      };

      openCommandPalette('隔离');
      const isolateIds = visibleCommandIds();
      await fireKey('Enter');
      const hiddenAfterIsolate = Object.fromEntries(model.components.map(c => [c.component_id, !!c.hidden]));

      openCommandPalette('显示全部');
      await fireKey('Enter');
      const hiddenAfterShowAll = Object.fromEntries(model.components.map(c => [c.component_id, !!c.hidden]));

      const input = document.getElementById('componentSearch');
      input.focus();
      input.value = 'sen';
      const typingCtrlK = await fireKey('k', {ctrlKey:true});
      const afterTyping = {
        prevented: typingCtrlK,
        focused: document.activeElement?.id,
        search: input.value,
        paletteHidden: document.getElementById('commandPalette')?.hidden,
      };

      return {hasApi, hasUi, afterOpen, searchIds, afterSelectAll, isolateIds, hiddenAfterIsolate, hiddenAfterShowAll, afterTyping};
    }"""
    )

    assert values["hasApi"] == {
        "commands": True,
        "open": True,
        "close": True,
        "run": True,
    }, values
    assert values["hasUi"] == {
        "button": True,
        "panel": True,
        "search": True,
        "list": True,
    }, values
    assert values["afterOpen"]["prevented"] is True, values
    assert values["afterOpen"]["hidden"] is False, values
    assert values["afterOpen"]["focused"] == "commandPaletteSearch", values
    assert values["afterOpen"]["resultCount"] >= 8, values
    assert values["searchIds"] == ["select-all-visible", "show-all-components"], values
    assert values["afterSelectAll"] == {
        "prevented": True,
        "hidden": True,
        "selected": ["guard", "sensor_a"],
        "primaryId": "sensor_a",
    }, values
    assert values["isolateIds"] == ["isolate-selection"], values
    assert values["hiddenAfterIsolate"]["sensor_a"] is False, values
    assert values["hiddenAfterIsolate"]["guard"] is False, values
    assert values["hiddenAfterIsolate"]["sensor_b"] is True, values
    assert values["hiddenAfterShowAll"] == {
        "world_volume": False,
        "sensor_a": False,
        "sensor_b": False,
        "guard": False,
    }, values
    assert values["afterTyping"] == {
        "prevented": False,
        "focused": "componentSearch",
        "search": "sen",
        "paletteHidden": True,
    }, values
    print(values)


if __name__ == "__main__":
    main()
