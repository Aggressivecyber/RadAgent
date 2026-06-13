from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:500,dy:500,dz:500}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'thin_detector', display_name:'Thin Detector', component_type:'layer', geometry_type:'box', dimensions:{dx:1000,dy:120,dz:0.5}, material_id:'Silicon', placement:{position:[0,0,10]}, mother_volume:'world_volume'},
        {component_id:'poly_pad', display_name:'Poly Pad', component_type:'electrode', geometry_type:'polycone', dimensions:{dx:30,dy:30,dz:4}, material_id:'Aluminum', placement:{position:[0,0,0]}, mother_volume:'world_volume', cross_section_polygon:[[0,20,-20],[0,45,-20],[0,45,5],[0,20,5]], cross_section_polygon_axes:{lateral:'y',depth:'z'}}
      ]}, 'dxf-export');
      setViewAxes('y','z');
      selectOnly('thin_detector');
      createDimensionsForSelection();
      const dxf = typeof buildSectionDXF === 'function' ? buildSectionDXF() : '';
      return {
        hasBuilder: typeof buildSectionDXF === 'function',
        hasExport: typeof exportDXF === 'function',
        hasButton: !!document.querySelector('[data-action="export-dxf"]'),
        startsSection: dxf.includes('0\\nSECTION\\n2\\nHEADER'),
        hasEntities: dxf.includes('0\\nSECTION\\n2\\nENTITIES'),
        ends: dxf.trim().endsWith('0\\nEOF'),
        hasUnits: dxf.includes('9\\n$INSUNITS\\n70\\n13'),
        hasAxesComment: dxf.includes('999\\nDevice Canvas section y-z units=um'),
        hasComponentLayer: dxf.includes('2\\nCOMP_THIN_DETECTOR'),
        hasAnnotationLayer: dxf.includes('2\\nANNOTATIONS'),
        hasThinPolyline: /0\\nLWPOLYLINE[\\s\\S]*8\\nCOMP_THIN_DETECTOR[\\s\\S]*90\\n4[\\s\\S]*10\\n-60(?:\\.0+)?\\n20\\n9\\.75(?:0+)?[\\s\\S]*10\\n60(?:\\.0+)?\\n20\\n10\\.25(?:0+)?/.test(dxf),
        hasPolygonPolyline: /0\\nLWPOLYLINE[\\s\\S]*8\\nCOMP_POLY_PAD[\\s\\S]*90\\n4[\\s\\S]*10\\n20(?:\\.0+)?\\n20\\n-20(?:\\.0+)?[\\s\\S]*10\\n45(?:\\.0+)?\\n20\\n5(?:\\.0+)?/.test(dxf),
        hasText: dxf.includes('0\\nTEXT') && dxf.includes('1\\nz 0.50 um') && dxf.includes('1\\ny 120 um'),
        noRaster: !dxf.includes('IMAGE') && !dxf.includes('HATCH'),
      };
    }"""
    )

    assert values["hasBuilder"], values
    assert values["hasExport"], values
    assert values["hasButton"], values
    assert values["startsSection"], values
    assert values["hasEntities"], values
    assert values["ends"], values
    assert values["hasUnits"], values
    assert values["hasAxesComment"], values
    assert values["hasComponentLayer"], values
    assert values["hasAnnotationLayer"], values
    assert values["hasThinPolyline"], values
    assert values["hasPolygonPolyline"], values
    assert values["hasText"], values
    assert values["noRaster"], values
    print(values)


if __name__ == "__main__":
    main()
