from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadExample();
      setViewAxes('y','z');
      selectedIds = new Set(['top_contact']);
      primaryId = 'top_contact';
      polyEditId = null;
      drawComponents();

      const c = model.components.find(x => x.component_id === 'top_contact');
      const n = rectNodes.get('top_contact');
      const bb = shapeBBoxPx(c);
      const grid = bgGroup.children
        .filter(x => x.className === 'Line')
        .map(x => ({
          strokeWidth: x.strokeWidth(),
          opacity: x.opacity(),
          strokeScale: x.strokeScaleEnabled(),
        }));
      const guides = thinSelectionGroup.children.map(x => ({
        strokeWidth: x.strokeWidth(),
        opacity: x.opacity(),
        strokeScale: x.strokeScaleEnabled(),
      }));

      return {
        projectedH: bb.h,
        shapeStroke: n.shape.strokeWidth(),
        shapeStrokeScale: n.shape.strokeScaleEnabled(),
        grid,
        guides,
      };
    }"""
    )

    assert values["projectedH"] < 0.2, values
    assert values["shapeStroke"] == 0, values
    assert values["shapeStrokeScale"] is False, values
    assert values["grid"], values
    assert all(item["strokeWidth"] <= 0.45 for item in values["grid"]), values
    assert all(item["opacity"] <= 0.55 for item in values["grid"]), values
    assert all(item["strokeScale"] is False for item in values["grid"]), values
    assert values["guides"], values
    assert all(item["strokeWidth"] <= 0.45 for item in values["guides"]), values
    assert all(item["opacity"] <= 0.7 for item in values["guides"]), values
    assert all(item["strokeScale"] is False for item in values["guides"]), values
    print(values)


if __name__ == "__main__":
    main()
