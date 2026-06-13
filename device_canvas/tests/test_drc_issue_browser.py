from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:100,dy:100,dz:100}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'outside', display_name:'Outside', component_type:'layer', geometry_type:'box', dimensions:{dx:30,dy:30,dz:30}, material_id:'Silicon', placement:{position:[50,0,0]}, mother_volume:'world_volume'},
        {component_id:'overlap_a', display_name:'Overlap A', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'SiO2', placement:{position:[-20,0,0]}, mother_volume:'world_volume'},
        {component_id:'overlap_b', display_name:'Overlap B', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'Aluminum', placement:{position:[-15,0,0]}, mother_volume:'world_volume'},
        {component_id:'warn_bad', display_name:'Warn bad', component_type:'layer', geometry_type:'box', dimensions:{dx:0,dy:20,dz:20}, material_id:'Silicon', placement:{position:[0,35,0]}, mother_volume:'world_volume'},
        {component_id:'warn_mother', display_name:'Warn mother', component_type:'layer', geometry_type:'box', dimensions:{dx:10,dy:10,dz:10}, material_id:'Silicon', placement:{position:[0,-35,0]}, mother_volume:'missing_container'}
      ]}, 'drc-issue-browser');
      setViewAxes('x','z');
      updateModelHealth();

      const hasUi = {
        filter: !!document.getElementById('issueSeverityFilter'),
        prev: !!document.querySelector('[data-action="issue-prev"]'),
        next: !!document.querySelector('[data-action="issue-next"]'),
        focus: !!document.querySelector('[data-action="issue-focus"]'),
        counter: !!document.getElementById('issueCursorLabel'),
      };
      const hasFns = {
        visible: typeof collectVisibleIssues === 'function',
        filter: typeof setIssueFilter === 'function',
        step: typeof stepIssue === 'function',
        focus: typeof focusCurrentIssue === 'function',
      };

      const allCodes = collectVisibleIssues().map(i => i.code);
      const initial = {
        filter: issueBrowserState.filter,
        cursor: issueBrowserState.cursor,
        countText: document.getElementById('issueCursorLabel').textContent,
        activeCode: getCurrentIssue().code,
        activeRows: Array.from(document.querySelectorAll('#issueList .issue-current')).map(el => el.dataset.issueId),
      };

      setIssueFilter('warn');
      const warnBefore = {
        filter: issueBrowserState.filter,
        codes: collectVisibleIssues().map(i => i.code),
        current: getCurrentIssue().code,
        rowKinds: Array.from(document.querySelectorAll('#issueList .issue')).map(el => ({
          warn: el.classList.contains('warn'),
          err: el.classList.contains('err'),
          current: el.classList.contains('issue-current'),
        })),
        countText: document.getElementById('issueCursorLabel').textContent,
      };
      stepIssue(1);
      const warnAfterStep = {
        cursor: issueBrowserState.cursor,
        current: getCurrentIssue().code,
        countText: document.getElementById('issueCursorLabel').textContent,
      };
      focusCurrentIssue();
      const warnFocused = Array.from(selectedIds).sort();

      setIssueFilter('fixable');
      const fixableBefore = {
        codes: collectVisibleIssues().map(i => i.code),
        current: getCurrentIssue().code,
        countText: document.getElementById('issueCursorLabel').textContent,
      };
      stepIssue(-1);
      const fixableAfterPrev = {
        cursor: issueBrowserState.cursor,
        current: getCurrentIssue().code,
      };
      focusCurrentIssue();
      const fixableFocused = Array.from(selectedIds).sort();

      setIssueFilter('none');
      const invalidFilter = issueBrowserState.filter;

      return {hasUi, hasFns, allCodes, initial, warnBefore, warnAfterStep, warnFocused, fixableBefore, fixableAfterPrev, fixableFocused, invalidFilter};
    }"""
    )

    assert all(values["hasUi"].values()), values
    assert all(values["hasFns"].values()), values
    assert set(values["allCodes"]) >= {"bad_dimensions", "missing_mother", "outside_world", "overlap3d"}, values
    assert values["initial"]["filter"] == "all", values
    assert values["initial"]["cursor"] == 0, values
    assert "1/" in values["initial"]["countText"], values
    assert values["initial"]["activeRows"], values

    assert values["warnBefore"]["filter"] == "warn", values
    assert values["warnBefore"]["codes"] == ["bad_dimensions", "missing_mother"], values
    assert values["warnBefore"]["current"] == "bad_dimensions", values
    assert values["warnBefore"]["countText"] == "1/2", values
    assert all(row["warn"] and not row["err"] for row in values["warnBefore"]["rowKinds"]), values
    assert sum(1 for row in values["warnBefore"]["rowKinds"] if row["current"]) == 1, values
    assert values["warnAfterStep"]["cursor"] == 1, values
    assert values["warnAfterStep"]["current"] == "missing_mother", values
    assert values["warnAfterStep"]["countText"] == "2/2", values
    assert values["warnFocused"] == ["warn_mother"], values

    assert values["fixableBefore"]["codes"] == ["outside_world", "overlap3d"], values
    assert values["fixableBefore"]["current"] == "outside_world", values
    assert values["fixableBefore"]["countText"] == "1/2", values
    assert values["fixableAfterPrev"]["cursor"] == 1, values
    assert values["fixableAfterPrev"]["current"] == "overlap3d", values
    assert values["fixableFocused"] == ["overlap_a", "overlap_b"], values
    assert values["invalidFilter"] == "all", values
    print(values)


if __name__ == "__main__":
    main()
