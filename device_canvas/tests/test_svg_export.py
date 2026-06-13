from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:500,dy:500,dz:500}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'thin_detector', display_name:'Thin Detector', component_type:'layer', geometry_type:'box', dimensions:{dx:1000,dy:120,dz:0.5}, material_id:'Silicon', placement:{position:[0,0,10]}, mother_volume:'world_volume'},
        {component_id:'poly_pad', display_name:'Poly Pad', component_type:'electrode', geometry_type:'polycone', dimensions:{dx:30,dy:30,dz:4}, material_id:'Aluminum', placement:{position:[0,0,0]}, mother_volume:'world_volume', cross_section_polygon:[[0,20,-20],[0,45,-20],[0,45,5],[0,20,5]], cross_section_polygon_axes:{lateral:'y',depth:'z'}}
      ]}, 'svg-export');
      setViewAxes('y','z');
      selectOnly('thin_detector');
      createDimensionsForSelection();
      const svg = buildSectionSVG();
      return {
        hasBuilder: typeof buildSectionSVG === 'function',
        hasExport: typeof exportSVG === 'function',
        hasButton: !!document.querySelector('[data-action="export-svg"]'),
        starts: svg.trim().startsWith('<svg '),
        hasAxes: svg.includes('data-lateral-axis="y"') && svg.includes('data-depth-axis="z"'),
        hasUnits: svg.includes('data-units="um"'),
        hasThinRect: /<rect[^>]+data-component-id="thin_detector"[^>]+width="120(?:\\.0+)?"[^>]+height="0\\.5(?:0+)?"/.test(svg),
        thinNotRasterized: !svg.includes('<image'),
        hasPolygon: /<polygon[^>]+data-component-id="poly_pad"[^>]+points="20,20 45,20 45,-5 20,-5"/.test(svg),
        hasAnnotation: svg.includes('data-annotation-kind="component_dimension"') && svg.includes('data-component-id="thin_detector"'),
        hasDepthLabel: svg.includes('z 0.50 um'),
        hasLateralLabel: svg.includes('y 120 um'),
        hasMetadata: svg.includes('<metadata>') && svg.includes('"componentCount":3'),
        hasVectorEffect: svg.includes('vector-effect="non-scaling-stroke"'),
      };
    }"""
    )

    assert values["hasBuilder"], values
    assert values["hasExport"], values
    assert values["hasButton"], values
    assert values["starts"], values
    assert values["hasAxes"], values
    assert values["hasUnits"], values
    assert values["hasThinRect"], values
    assert values["thinNotRasterized"], values
    assert values["hasPolygon"], values
    assert values["hasAnnotation"], values
    assert values["hasDepthLabel"], values
    assert values["hasLateralLabel"], values
    assert values["hasMetadata"], values
    assert values["hasVectorEffect"], values
    print(values)


if __name__ == "__main__":
    main()
