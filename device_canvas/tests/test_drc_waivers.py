from browser_helpers import evaluate_in_page


def main():
    values = evaluate_in_page(
        """() => {
      loadModel({components:[
        {component_id:'world_volume', display_name:'World', component_type:'world', geometry_type:'box', dimensions:{dx:100,dy:100,dz:100}, material_id:'Air', placement:{position:[0,0,0]}},
        {component_id:'outside', display_name:'Outside', component_type:'layer', geometry_type:'box', dimensions:{dx:30,dy:30,dz:30}, material_id:'Silicon', placement:{position:[50,0,0]}, mother_volume:'world_volume'},
        {component_id:'overlap_a', display_name:'Overlap A', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'SiO2', placement:{position:[-20,0,0]}, mother_volume:'world_volume'},
        {component_id:'overlap_b', display_name:'Overlap B', component_type:'layer', geometry_type:'box', dimensions:{dx:20,dy:20,dz:20}, material_id:'Aluminum', placement:{position:[-15,0,0]}, mother_volume:'world_volume'}
      ]}, 'drc-waivers');
      setViewAxes('x','z');
      updateModelHealth();

      const hasFns = {
        signature: typeof issueSignature === 'function',
        waive: typeof waiveIssue === 'function',
        revoke: typeof revokeIssueWaiver === 'function',
        waived: typeof isIssueWaived === 'function',
      };
      const hasUi = {
        filterOption: !!document.querySelector('#issueSeverityFilter option[value="waived"]'),
      };
      const before = {
        all: collectVisibleIssues().map(i => i.code),
        fixable: (setIssueFilter('fixable'), collectVisibleIssues().map(i => i.code)),
      };
      setIssueFilter('all');
      const outsideIssue = collectModelIssues().issues.find(i => i.code === 'outside_world');
      const signature = issueSignature(outsideIssue);
      const waived = waiveIssue(outsideIssue.id, 'Known calibration envelope');
      const afterWaive = {
        waived,
        isWaived:isIssueWaived(outsideIssue),
        all: collectVisibleIssues().map(i => i.code),
        activeRows:Array.from(document.querySelectorAll('#issueList .issue')).map(el => ({text:el.textContent, waived:el.classList.contains('issue-waived')})),
        metrics:document.getElementById('healthMetrics').textContent,
      };
      setIssueFilter('fixable');
      const fixableAfterWaive = collectVisibleIssues().map(i => i.code);
      setIssueFilter('waived');
      const waivedView = {
        filter: issueBrowserState.filter,
        codes: collectVisibleIssues().map(i => i.code),
        text:document.getElementById('issueList').textContent,
      };
      const report = modelHealthReportText();
      const exported = buildDeviceCanvasState().drcWaivers;

      drcWaivers = [];
      applyDeviceCanvasState({drcWaivers: exported});
      const restoredWaiver = drcWaivers[0];
      const restoredIsWaived = isIssueWaived(outsideIssue);
      const revoked = revokeIssueWaiver(signature);
      setIssueFilter('all');
      const afterRevoke = {
        revoked,
        all: collectVisibleIssues().map(i => i.code),
        waivedCount: drcWaivers.length,
      };

      return {hasFns, hasUi, before, signature, afterWaive, fixableAfterWaive, waivedView, report, exported, restoredWaiver, restoredIsWaived, afterRevoke};
    }"""
    )

    assert all(values["hasFns"].values()), values
    assert all(values["hasUi"].values()), values
    assert values["before"]["all"] == ["outside_world", "overlap3d"], values
    assert values["before"]["fixable"] == ["outside_world", "overlap3d"], values
    assert values["signature"].startswith("outside_world:"), values
    assert values["afterWaive"]["waived"], values
    assert values["afterWaive"]["isWaived"], values
    assert values["afterWaive"]["all"] == ["overlap3d"], values
    assert "活动问题" in values["afterWaive"]["metrics"], values
    assert values["fixableAfterWaive"] == ["overlap3d"], values
    assert values["waivedView"]["filter"] == "waived", values
    assert values["waivedView"]["codes"] == ["outside_world"], values
    assert "Known calibration envelope" in values["waivedView"]["text"], values
    assert "已豁免" in values["report"], values
    assert "Known calibration envelope" in values["report"], values
    assert values["exported"][0]["signature"] == values["signature"], values
    assert values["exported"][0]["reason"] == "Known calibration envelope", values
    assert values["restoredWaiver"]["signature"] == values["signature"], values
    assert values["restoredIsWaived"], values
    assert values["afterRevoke"]["revoked"], values
    assert values["afterRevoke"]["all"] == ["outside_world", "overlap3d"], values
    assert values["afterRevoke"]["waivedCount"] == 0, values
    print(values)


if __name__ == "__main__":
    main()
