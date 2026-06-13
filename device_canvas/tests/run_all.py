import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TESTS = [
    ["node", "device_canvas/tests/core_geometry.test.js"],
    [sys.executable, "device_canvas/tests/test_cad_status_bar.py"],
    [sys.executable, "device_canvas/tests/test_clipboard_copy_paste.py"],
    [sys.executable, "device_canvas/tests/test_2d_edit_world_constraints.py"],
    [sys.executable, "device_canvas/tests/test_2d_mirror_rotate.py"],
    [sys.executable, "device_canvas/tests/test_3d_preview_thin_edges.py"],
    [sys.executable, "device_canvas/tests/test_3d_preview_interaction.py"],
    [sys.executable, "device_canvas/tests/test_3d_align_controls.py"],
    [sys.executable, "device_canvas/tests/test_3d_transform_controls.py"],
    [sys.executable, "device_canvas/tests/test_3d_world_constraints.py"],
    [sys.executable, "device_canvas/tests/test_boundary_clamp_mode.py"],
    [sys.executable, "device_canvas/tests/test_assembly_tree.py"],
    [sys.executable, "device_canvas/tests/test_component_list_filters.py"],
    [sys.executable, "device_canvas/tests/test_component_rename.py"],
    [sys.executable, "device_canvas/tests/test_command_palette.py"],
    [sys.executable, "device_canvas/tests/test_component_dimension_annotations.py"],
    [sys.executable, "device_canvas/tests/test_csv_reports.py"],
    [sys.executable, "device_canvas/tests/test_drc_issue_browser.py"],
    [sys.executable, "device_canvas/tests/test_drc_rule_deck.py"],
    [sys.executable, "device_canvas/tests/test_drc_waivers.py"],
    [sys.executable, "device_canvas/tests/test_dxf_export.py"],
    [sys.executable, "device_canvas/tests/test_dxf_import.py"],
    [sys.executable, "device_canvas/tests/test_dxf_import_bulge.py"],
    [sys.executable, "device_canvas/tests/test_dxf_import_curves.py"],
    [sys.executable, "device_canvas/tests/test_distribute_3d_gaps.py"],
    [sys.executable, "device_canvas/tests/test_keyboard_shortcuts.py"],
    [sys.executable, "device_canvas/tests/test_layer_group_manager.py"],
    [sys.executable, "device_canvas/tests/test_marquee_selection.py"],
    [sys.executable, "device_canvas/tests/test_pair_gap_annotations.py"],
    [sys.executable, "device_canvas/tests/test_polygon_node_editing.py"],
    [sys.executable, "device_canvas/tests/test_polygon_vertex_commands.py"],
    [sys.executable, "device_canvas/tests/test_polygon_vertex_inputs.py"],
    [sys.executable, "device_canvas/tests/test_safe_copy_array.py"],
    [sys.executable, "device_canvas/tests/test_section_overlap_touching.py"],
    [sys.executable, "device_canvas/tests/test_selection_pair_gap_adjust.py"],
    [sys.executable, "device_canvas/tests/test_selection_pair_probe.py"],
    [sys.executable, "device_canvas/tests/test_selection_sets.py"],
    [sys.executable, "device_canvas/tests/test_snap_settings.py"],
    [sys.executable, "device_canvas/tests/test_stack_gap_commands.py"],
    [sys.executable, "device_canvas/tests/test_svg_export.py"],
    [sys.executable, "device_canvas/tests/test_visibility_isolation.py"],
    [sys.executable, "device_canvas/tests/test_view_states.py"],
    [sys.executable, "device_canvas/tests/test_yz_auxiliary_hairlines.py"],
    [sys.executable, "device_canvas/tests/test_yz_thin_layers.py"],
    [sys.executable, "device_canvas/tests/test_yz_thin_selection.py"],
    [sys.executable, "device_canvas/tests/test_yz_ultrathin_auxiliary_scale.py"],
    [sys.executable, "device_canvas/tests/test_yz_ultrathin_suppresses_strokes.py"],
    [sys.executable, "device_canvas/tests/test_yz_zoomed_thin_strokes.py"],
]


def main():
    for cmd in TESTS:
        print("$ " + " ".join(cmd), flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True)
    print(f"device_canvas tests passed: {len(TESTS)}")


if __name__ == "__main__":
    main()
