from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:200,dy:200,dz:200}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'left', display_name:'Left', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'Silicon', placement:{position:[-10,0,0]}, mother_volume:'world_volume'},
        {component_id:'touching', display_name:'Touching', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'SiO2', placement:{position:[10,0,0]}, mother_volume:'world_volume'},
        {component_id:'overlap', display_name:'Overlap', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'Aluminum', placement:{position:[25,0,0]}, mother_volume:'world_volume'}
      ]}, 'section-overlap-touching');
      setViewAxes('x','z');
      const initial = detectSectionOverlaps();
      model.components.find(c => c.component_id === 'overlap').hidden = true;
      drawComponents();
      const touchingOnly = detectSectionOverlaps();
      return {
        initialPairs: initial.pairs,
        initialRegions: initial.regions.length,
        touchingPairs: touchingOnly.pairs,
        touchingRegions: touchingOnly.regions.length,
        touchingIds: Array.from(touchingOnly.ids),
        hudDisplay: document.getElementById('hudOverlap').style.display,
        renderedRegions: overlapGroup.children.length,
      };
    }"""
    )

    assert values["initialPairs"] == [["touching", "overlap"]], values
    assert values["initialRegions"] == 1, values
    assert values["touchingPairs"] == [], values
    assert values["touchingRegions"] == 0, values
    assert values["touchingIds"] == [], values
    assert values["hudDisplay"] == "none", values
    assert values["renderedRegions"] == 0, values
    print(values)


if __name__ == "__main__":
    main()
