# User-supplied AnalysisAlgorithmsConfig text-config yaml, shipped verbatim.
import logging
logging.basicConfig(level=logging.INFO)

_servicex_custom_yaml_text = {{ custom_yaml_python_literal }}

_servicex_custom_yaml_path = 'servicex_custom_config.yaml'
with open(_servicex_custom_yaml_path, 'w') as _f:
    _f.write(_servicex_custom_yaml_text)

from AnalysisAlgorithmsConfig.ConfigText import TextConfig
config = TextConfig(_servicex_custom_yaml_path)
