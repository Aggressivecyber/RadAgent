from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadExample();
      setViewAxes('y','z');
      return ['oxide','top_contact','si_window','back_contact'].map(id => {
        const c = model.components.find(x => x.component_id === id);
        const n = rectNodes.get(id);
        const rawH = c.dimensions.dz * camera.sDep;
        return {
          id,
          rawH,
          renderedH: n.shape.height(),
          stroke: n.shape.strokeWidth(),
          hit: n.shape.hitStrokeWidth(),
        };
      });
    }"""
    )

    for item in values:
        assert item["rawH"] < 1, values
        assert abs(item["renderedH"] - item["rawH"]) < 1e-6, values
        assert item["stroke"] == 0, values
        assert item["hit"] >= 6, values
    print(values)


if __name__ == "__main__":
    main()
