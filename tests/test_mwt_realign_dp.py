from __future__ import annotations

from debug_store import clear_mwt_realign_traces, get_mwt_realign_traces
from pipeline_common import _mwt_probe_text, _realign_mwt_children


def _run_case(probes, surface):
    parts = [{"text": probe, "lemma": probe} for probe in probes]
    _realign_mwt_children(parts, surface)
    return parts


def _assert_full_coverage(parts, surface):
    cursor = 0
    for idx, part in enumerate(parts):
        probe = _mwt_probe_text(part)
        surface_slice = part.get("surface_slice")
        char_map = part.get("surface_char_map")

        assert isinstance(surface_slice, list) and len(surface_slice) == 2, (
            f"part {idx} missing surface_slice: {surface_slice!r}"
        )
        assert isinstance(char_map, list), f"part {idx} missing char_map"

        start, end = surface_slice
        assert start == cursor, f"part {idx} broke contiguity: expected {cursor}, got {start}"
        assert end >= start, f"part {idx} has negative width slice: {surface_slice!r}"
        if probe:
            assert end > start, f"part {idx} collapsed to zero width: {surface_slice!r}"
        assert len(char_map) == len(probe), (
            f"part {idx} char_map length mismatch: {len(char_map)} != {len(probe)}"
        )
        if end > start:
            for mapped in char_map:
                assert start <= mapped < end, (
                    f"part {idx} char_map value {mapped} escaped slice {surface_slice!r}"
                )
        cursor = end

    assert cursor == len(surface), (
        f"slices did not cover full surface: ended at {cursor}, len={len(surface)}"
    )


def test_sanskrit_duplicate_ca():
    surface = "sthālyāścānūpyāścauṣadhīḥ"
    probes = ["sthālyāḥ", "ca", "anūpyāḥ", "ca", "oṣadhīḥ"]
    parts = _run_case(probes, surface)

    _assert_full_coverage(parts, surface)
    assert parts[3]["_realign_pass"] == "dp"
    assert parts[3]["surface_slice"] == [16, 18], parts
    assert surface[16:18] == "ca"


def test_trivial_fast_path():
    surface = "deles"
    probes = ["de", "les"]
    parts = _run_case(probes, surface)

    _assert_full_coverage(parts, surface)
    assert [part["_realign_pass"] for part in parts] == ["trivial", "trivial"]
    assert [part["surface_slice"] for part in parts] == [[0, 2], [2, 5]]


def test_nontrivial_no_exact_child():
    surface = "aXcY"
    probes = ["ab", "cd"]
    parts = _run_case(probes, surface)

    _assert_full_coverage(parts, surface)
    assert [part["_realign_pass"] for part in parts] == ["dp", "dp"]
    assert all(
        surface[s[0] : s[1]] != probes[i]
        for i, s in enumerate(part["surface_slice"] for part in parts)
    )


def test_repeated_short_token_resolved_globally():
    surface = "nātina"
    probes = ["na", "ti", "na"]
    parts = _run_case(probes, surface)

    _assert_full_coverage(parts, surface)
    assert parts[2]["surface_slice"] == [4, 6], parts
    assert surface[4:6] == "na"


def test_debug_trace_shape():
    clear_mwt_realign_traces()
    _run_case(["sthālyāḥ", "ca", "anūpyāḥ", "ca", "oṣadhīḥ"], "sthālyāścānūpyāścauṣadhīḥ")

    traces = get_mwt_realign_traces()
    assert traces, "expected at least one realign trace"
    trace = traces[0]
    assert trace.get("note") == "dp", trace
    children = trace.get("children")
    assert isinstance(children, list) and children, trace
    for child in children:
        opcodes = child.get("opcodes")
        assert isinstance(opcodes, list), child
        for opcode in opcodes:
            assert isinstance(opcode, (list, tuple)) and len(opcode) == 5, opcode


def main():
    test_sanskrit_duplicate_ca()
    test_trivial_fast_path()
    test_nontrivial_no_exact_child()
    test_repeated_short_token_resolved_globally()
    test_debug_trace_shape()
    print("MWT DP realignment regression checks passed.")


if __name__ == "__main__":
    main()
