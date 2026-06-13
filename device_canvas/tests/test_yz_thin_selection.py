from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadExample();
      setViewAxes('y','z');
      selectOnly('top_contact');
      const c = model.components.find(x => x.component_id === 'top_contact');
      const n = rectNodes.get('top_contact');
      const bb = shapeBBoxPx(c);
      return {
        projectedH: bb.h,
        stroke: n.shape.strokeWidth(),
        opacity: n.shape.opacity(),
        hit: n.shape.hitStrokeWidth(),
        guideCount: thinSelectionGroup.children.length,
        selected: selectedIds.has('top_contact'),
        transformerNodes: tr.nodes().map(x => x.getAttr('cid')),
        transformerBorder: tr.borderStrokeWidth(),
        transformerAnchor: tr.anchorSize(),
      };
    }"""
    )

    assert values["projectedH"] < 1, values
    assert values["stroke"] == 0, values
    assert 0 < values["opacity"] <= 0.2, values
    assert values["hit"] >= 6, values
    assert values["guideCount"] >= 4, values
    assert values["selected"], values
    assert values["transformerNodes"] == [], values
    assert values["transformerBorder"] <= 0.5, values
    assert values["transformerAnchor"] <= 5, values
    print(values)


if __name__ == "__main__":
    main()
