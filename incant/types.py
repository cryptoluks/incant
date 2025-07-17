"""
Type definitions for Incant.
"""

from typing import Dict, List, Optional, Union, Any
from pathlib import Path

# Type aliases for better readability
InstanceName = str
ProjectName = str
ImageName = str
CommandList = List[str]
ConfigDict = Dict[str, Any]

# Instance configuration types
InstanceConfig = Dict[str, Union[str, int, bool, float]]
DeviceConfig = Dict[str, Dict[str, str]]
ProvisionStep = Union[str, List[str]]

# Complete instance definition
InstanceDefinition = Dict[
    str, Union[ImageName, bool, List[str], InstanceConfig, DeviceConfig, str, ProvisionStep]
]

# Full configuration structure
IncantConfig = Dict[str, Union[bool, Dict[str, InstanceDefinition]]]

# CLI options
CliOptions = Dict[str, Union[bool, str, Optional[Path]]]
