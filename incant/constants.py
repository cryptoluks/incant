"""
Constants and shared configuration for Incant.
"""

# Click output styles used throughout the application
CLICK_STYLE = {
    "success": {"fg": "green", "bold": True},
    "info": {"fg": "cyan"},
    "warning": {"fg": "yellow"},
    "error": {"fg": "red"},
}

# Configuration file patterns to search for
CONFIG_FILE_PATTERNS = [
    "incant.yaml",
    "incant.yaml.j2",
    "incant.yaml.mako",
    ".incant.yaml",
    ".incant.yaml.j2",
    ".incant.yaml.mako",
]

# Default configuration example for init command
DEFAULT_CONFIG_TEMPLATE = """\
project: true

instances:
  webserver:
    image: images:debian/13
    vm: true
    devices:
      root:
        size: 20GB
    config:
      limits.processes: 100
    type: c2-m2
    provision:
      - apt-get update && apt-get -y install curl
      - |
        #!/bin/bash
        set -xe
        echo Done!
"""
