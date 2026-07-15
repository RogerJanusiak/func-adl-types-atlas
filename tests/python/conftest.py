import ast
import importlib
import shutil
import sys
from pathlib import Path

import pytest

# The metadata source directory in this repo. Tests assemble a temporary
# package from it that mirrors the layout of a generated type package (e.g.
# func_adl_servicex_xaodr25): helper .py files at the package root and the
# jinja templates in a `templates/` subdirectory (see src/helper_files.cpp).
METADATA_DIR = Path(__file__).parent.parent.parent / "metadata"

HELPER_FILES = [
    "calibration_support.py",
    "calibration_event_config.py",
    "metadata_for_collections.py",
    "default_calibration_config.py",
]

TEMPLATE_FILES = [
    "sys_error_tool.py",
    "pileup_tool.py",
    "corrections_jet.py",
    "corrections_electron.py",
    "corrections_photon.py",
    "corrections_muon.py",
    "corrections_tau.py",
    "corrections_overlap.py",
    "corrections_met.py",
    "add_calibration_to_job.py",
    "custom_config_yaml.py",
]


def _build_package(root: Path, pkg_name: str, release_dirs) -> object:
    """Copy the metadata files into a package layout mirroring a generated
    type package and import it. `release_dirs` is the release search order
    (most specific first), mimicking metadata_file_finder.cpp."""
    pkg = root / pkg_name
    (pkg / "templates").mkdir(parents=True)

    search_dirs = [METADATA_DIR / d for d in release_dirs] + [METADATA_DIR]

    def find(name: str) -> Path:
        for d in search_dirs:
            if (d / name).exists():
                return d / name
        raise FileNotFoundError(name)

    for f in HELPER_FILES:
        shutil.copy(find(f), pkg / f)
    for f in TEMPLATE_FILES:
        shutil.copy(find(f), pkg / "templates" / f)
    (pkg / "__init__.py").write_text(
        "from .calibration_support import CalibrationEventConfig, calib_tools\n"
    )

    sys.path.insert(0, str(root))
    try:
        return importlib.import_module(pkg_name)
    finally:
        sys.path.remove(str(root))


@pytest.fixture(scope="session")
def pkg_r25(tmp_path_factory):
    "Package assembled with the release 25 metadata (TextConfig based)."
    return _build_package(tmp_path_factory.mktemp("r25"), "sx_calib_r25", ["25"])


@pytest.fixture(scope="session")
def pkg_base(tmp_path_factory):
    "Package assembled with only the base (release 21) metadata."
    return _build_package(tmp_path_factory.mktemp("base"), "sx_calib_base", [])


def job_script_blocks(stream):
    "Return all `add_job_script` metadata dicts found in a query's ast."
    blocks = []
    for node in ast.walk(stream.query_ast):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "MetaData"
        ):
            try:
                d = ast.literal_eval(node.args[1])
            except ValueError:
                continue
            if isinstance(d, dict) and d.get("metadata_type") == "add_job_script":
                blocks.append(d)
    return blocks
