from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({
        components: [
          {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:5000,dy:5000,dz:5000}, material_id:'Air', placement:{position:[0,0,0]}},
          {component_id:'detector', display_name:'Thin side detector', component_type:'layer', geometry_type:'box', dimensions:{dx:1000,dy:1000,dz:50}, material_id:'Silicon', placement:{position:[0,0,0]}, mother_volume:'world_volume'}
        ]
      }, 'zoomed-thin-test');
      setViewAxes('y','z');
      selectOnly('detector');
      const c = model.components.find(x => x.component_id === 'detector');
      const rawH = shapeBBoxPx(c).h;
      const beforeStroke = rectNodes.get('detector').shape.strokeWidth();
      zoomBy(0.05);
      const screenH = shapeBBoxPx(c).h * stage.scaleY();
      const stroke = rectNodes.get('detector').shape.strokeWidth();
      const thinMin = thinProjectionMinPx();
      const grid = bgGroup.children
        .filter(x => x.className === 'Line')
        .map(x => Number(x.strokeWidth()) || 0);
      return {
        rawH,
        beforeStroke,
        screenH,
        stageScale: stage.scaleY(),
        stroke,
        thinMin,
        gridMax: Math.max(...grid),
      };
    }"""
    )

    assert values["rawH"] > 2, values
    assert values["screenH"] < 1, values
    assert values["thinMin"] is not None and values["thinMin"] < 1, values
    assert values["stroke"] == 0, values
    assert values["gridMax"] == 0, values
    print(values)


if __name__ == "__main__":
    main()
