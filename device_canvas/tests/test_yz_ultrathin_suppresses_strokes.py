from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadExample();
      setViewAxes('y','z');
      selectOnly('top_contact');
      showSnapLines([{axis:'x',pos:X(0)},{axis:'y',pos:Y(253)}]);
      measureState = {start:{lat:-500,dep:252}, end:{lat:500,dep:252}, preview:null};
      drawMeasurement();
      createDimensionsForSelection();
      drawAnnotations();

      const thinMin = thinProjectionMinPx();
      const groups = [
        ['grid', bgGroup],
        ['selection', thinSelectionGroup],
        ['snap', snapGroup],
        ['measure', measureGroup],
        ['annotation', annotationGroup],
        ['overlap', overlapGroup],
      ];
      const nonzeroStrokes = [];
      function collectStrokes(groupName, node) {
        if (typeof node.strokeWidth === 'function' && typeof node.stroke === 'function') {
          const stroke = node.stroke();
          const sw = Number(node.strokeWidth()) || 0;
          if (stroke && sw > 0) {
            nonzeroStrokes.push({group:groupName, type:node.className, strokeWidth:sw});
          }
        }
        if (typeof node.getChildren === 'function') {
          node.getChildren().forEach(child => collectStrokes(groupName, child));
        }
      }
      for (const [name, group] of groups) {
        collectStrokes(name, group);
      }
      const componentStrokes = [...rectNodes.values()].map(n => ({
        id:n.shape.getAttr('cid'),
        strokeWidth:Number(n.shape.strokeWidth()) || 0,
      }));
      return {thinMin, nonzeroStrokes, componentStrokes};
    }"""
    )

    assert values["thinMin"] < 1, values
    assert values["nonzeroStrokes"] == [], values
    assert all(item["strokeWidth"] == 0 for item in values["componentStrokes"]), values
    print(values)


if __name__ == "__main__":
    main()
