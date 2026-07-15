import ast
from pathlib import Path

import pytest
from func_adl import EventDataset

from conftest import job_script_blocks

GOOD_YAML = """\
CommonServices:
  runSystematics: false

Electrons:
  - containerName: 'MyElectrons'
    WorkingPoint:
      - selectionName: 'loose'
        identificationWP: 'MediumLHElectron'
        isolationWP: 'NonIso'

Thinning:
  - containerName: 'MyElectrons'
    outputName: 'OutElectrons'
    selectionName: 'loose'
"""


class _ds(EventDataset):
    async def execute_result_async(self, a, title=None):
        return None


@pytest.fixture
def yaml_file(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text(GOOD_YAML)
    return f


def _query_with_yaml(pkg, yaml_file):
    return pkg.calib_tools.query_update(_ds(), custom_config_yaml_path=str(yaml_file))


def _accessor_call(name: str) -> ast.Call:
    return ast.parse(f"e.{name}()").body[0].value


def test_electron_accessor_emits_custom_blocks(pkg_r25, yaml_file):
    q = _query_with_yaml(pkg_r25, yaml_file)
    new_s, new_call = pkg_r25.calibration_support.fixup_collection_call(
        q, _accessor_call("Electrons"), "electron_collection"
    )

    blocks = {b["name"]: b for b in job_script_blocks(new_s)}
    assert set(blocks) == {"custom_config_yaml", "add_calibration_to_job"}
    assert "depends_on" not in blocks["custom_config_yaml"]
    assert blocks["add_calibration_to_job"]["depends_on"] == ["custom_config_yaml"]

    script = "\n".join(blocks["custom_config_yaml"]["script"])
    assert "TextConfig(_servicex_custom_yaml_path)" in script

    assert ast.literal_eval(new_call.args[0]) == "OutElectrons_NOSYS"


def test_jet_accessor_output_name(pkg_r25, yaml_file):
    q = _query_with_yaml(pkg_r25, yaml_file)
    _, new_call = pkg_r25.calibration_support.fixup_collection_call(
        q, _accessor_call("Jets"), "jet_collection"
    )

    # Default PHYS config has jet_collection == AntiKt4EMPFlowJets
    assert ast.literal_eval(new_call.args[0]) == "AntiKt4EMPFlowJets_Calib_NOSYS"


def test_yaml_text_round_trips(pkg_r25, tmp_path):
    tricky = "a: \"quoted\"\nb: 'single'\nc: {{ not_jinja }}\nd: |\n  block\n"
    f = tmp_path / "tricky.yaml"
    f.write_text(tricky)

    q = _query_with_yaml(pkg_r25, f)
    new_s, _ = pkg_r25.calibration_support.fixup_collection_call(
        q, _accessor_call("Electrons"), "electron_collection"
    )

    blocks = {b["name"]: b for b in job_script_blocks(new_s)}
    prefix = "_servicex_custom_yaml_text = "
    (literal_line,) = [
        ln for ln in blocks["custom_config_yaml"]["script"] if ln.startswith(prefix)
    ]
    embedded = ast.literal_eval(literal_line.removeprefix(prefix))
    assert embedded == tricky


def test_systematics_rejected(pkg_r25, yaml_file):
    q = _query_with_yaml(pkg_r25, yaml_file)
    # A query node between the two QMetaData calls, as in a real query -
    # func_adl replaces (not merges) _q_metadata applied twice to the same
    # ast node.
    q = q.Select(lambda e: e)
    q = pkg_r25.calib_tools.query_sys_error(q, "EG_SCALE_ALL__1up")

    with pytest.raises(ValueError, match="not supported"):
        pkg_r25.calibration_support.fixup_collection_call(
            q, _accessor_call("Electrons"), "electron_collection"
        )


def test_yaml_enabling_systematics_rejected(pkg_r25, tmp_path):
    f = tmp_path / "sys.yaml"
    f.write_text("CommonServices:\n  runSystematics: true\n")

    with pytest.raises(ValueError, match="runSystematics"):
        _query_with_yaml(pkg_r25, f)


def test_empty_yaml_rejected(pkg_r25, tmp_path):
    f = tmp_path / "empty.yaml"
    f.write_text("\n")

    with pytest.raises(ValueError, match="empty"):
        _query_with_yaml(pkg_r25, f)


def test_met_not_supported(pkg_r25, yaml_file):
    q = _query_with_yaml(pkg_r25, yaml_file)

    with pytest.raises(NotImplementedError, match="met_collection"):
        pkg_r25.calibration_support.fixup_collection_call(
            q, _accessor_call("MissingET"), "met_collection"
        )


def test_missing_yaml_file(pkg_r25, tmp_path):
    with pytest.raises(ValueError, match="not found"):
        pkg_r25.calib_tools.query_update(
            _ds(), custom_config_yaml_path=str(tmp_path / "nope.yaml")
        )


def test_path_object_accepted_and_stored_as_str(pkg_r25, yaml_file):
    q = pkg_r25.calib_tools.query_update(_ds(), custom_config_yaml_path=Path(yaml_file))
    config = pkg_r25.calib_tools.query_get(q)
    assert isinstance(config.custom_config_yaml_path, str)
    assert Path(config.custom_config_yaml_path) == yaml_file.resolve()


def test_uncalibrated_accessor_unaffected(pkg_r25, yaml_file):
    q = _query_with_yaml(pkg_r25, yaml_file)
    call = ast.parse("e.Jets('MyJets', False)").body[0].value
    new_s, new_call = pkg_r25.calibration_support.fixup_collection_call(
        q, call, "jet_collection"
    )

    assert job_script_blocks(new_s) == []
    assert ast.literal_eval(new_call.args[0]) == "MyJets"


def test_release_21_not_supported(pkg_base, yaml_file):
    q = _query_with_yaml(pkg_base, yaml_file)

    with pytest.raises(NotImplementedError, match="release 25"):
        pkg_base.calibration_support.fixup_collection_call(
            q, _accessor_call("Electrons"), "electron_collection"
        )


def test_repeated_accessors_emit_identical_blocks(pkg_r25, yaml_file):
    q = _query_with_yaml(pkg_r25, yaml_file)
    s1, _ = pkg_r25.calibration_support.fixup_collection_call(
        q, _accessor_call("Electrons"), "electron_collection"
    )
    s2, _ = pkg_r25.calibration_support.fixup_collection_call(
        s1, _accessor_call("Muons"), "muon_collection"
    )

    custom_blocks = [
        b for b in job_script_blocks(s2) if b["name"] == "custom_config_yaml"
    ]
    assert len(custom_blocks) == 2
    assert custom_blocks[0] == custom_blocks[1]
