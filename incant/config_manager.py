"""
Configuration management for Incant.
"""

import os
import sys
from pathlib import Path
from typing import Optional

import click
import yaml
from jinja2 import Environment, FileSystemLoader
from mako.template import Template

from .constants import CLICK_STYLE, CONFIG_FILE_PATTERNS, DEFAULT_CONFIG_TEMPLATE
from .exceptions import ConfigurationError
from .types import IncantConfig, CliOptions


class ConfigurationManager:
    """Handles loading, parsing, and processing of configuration files."""

    def __init__(self, options: CliOptions):
        self.verbose = options.get("verbose", False)
        self.config_path = options.get("config")
        self.quiet = options.get("quiet", False)
        self.no_config = options.get("no_config", False)

    def find_config_file(self) -> Optional[Path]:
        """Find the configuration file to use."""
        search_paths = []

        # If a specific config is provided, check it first
        if self.config_path:
            search_paths.append(Path(self.config_path))

        # Add default patterns in current directory
        current_dir = Path.cwd()
        for pattern in CONFIG_FILE_PATTERNS:
            search_paths.append(current_dir / pattern)

        for path in search_paths:
            if path.is_file():
                if self.verbose:
                    click.secho(f"Config found at: {path}", **CLICK_STYLE["success"])
                return path

        return None

    def _process_template(self, content: str, config_file: Path) -> str:
        """Process template content based on file extension."""
        if config_file.suffix == ".j2":
            if self.verbose:
                click.secho("Using Jinja2 template processing...", **CLICK_STYLE["info"])
            env = Environment(loader=FileSystemLoader(os.getcwd()))
            template = env.from_string(content)
            return template.render()

        elif config_file.suffix == ".mako":
            if self.verbose:
                click.secho("Using Mako template processing...", **CLICK_STYLE["info"])
            template = Template(content)
            return template.render()

        return content

    def load_config(self) -> Optional[IncantConfig]:
        """Load and parse the configuration file."""
        if self.no_config:
            return None

        config_file = self.find_config_file()
        if config_file is None:
            if not self.quiet:
                click.secho("No config file found to load.", **CLICK_STYLE["error"])
            return None

        try:
            # Read the config file content
            with open(config_file, "r", encoding="utf-8") as file:
                content = file.read()

            # Process templates if needed
            content = self._process_template(content, config_file)

            # Parse YAML
            config_data = yaml.safe_load(content)

            if self.verbose:
                click.secho(
                    f"Config loaded successfully from {config_file}",
                    **CLICK_STYLE["success"],
                )
            return config_data

        except yaml.YAMLError as e:
            raise ConfigurationError(f"Error parsing YAML file: {e}")
        except FileNotFoundError:
            raise ConfigurationError(f"Config file not found: {config_file}")
        except Exception as e:
            raise ConfigurationError(f"Error loading configuration: {e}")

    def validate_config(self, config: IncantConfig) -> None:
        """Validate that the configuration has required fields."""
        if not config:
            raise ConfigurationError("Configuration is empty")

        if "instances" not in config:
            raise ConfigurationError("No instances found in config")

        instances = config["instances"]
        if not isinstance(instances, dict):
            raise ConfigurationError("Instances must be a dictionary")

        for name, instance_def in instances.items():
            if not isinstance(instance_def, dict):
                raise ConfigurationError(f"Instance '{name}' definition must be a dictionary")
            if "image" not in instance_def:
                raise ConfigurationError(f"Instance '{name}' must have an 'image' field")

    def dump_config(self, config: IncantConfig) -> None:
        """Dump configuration to stdout."""
        if not config:
            raise ConfigurationError("No configuration to dump")

        try:
            yaml.dump(config, sys.stdout, default_flow_style=False, sort_keys=False)
        except Exception as e:
            raise ConfigurationError(f"Error dumping configuration: {e}")

    def create_example_config(self, filename: str = "incant.yaml") -> None:
        """Create an example configuration file."""
        config_path = Path(filename)

        if config_path.exists():
            raise ConfigurationError(f"{filename} already exists. Aborting.")

        try:
            with open(config_path, "w") as f:
                f.write(DEFAULT_CONFIG_TEMPLATE)
            click.secho(f"Example configuration written to {filename}", **CLICK_STYLE["success"])
        except Exception as e:
            raise ConfigurationError(f"Error creating configuration file: {e}")
