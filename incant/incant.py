import sys
from typing import Optional

import click

from .config_manager import ConfigurationManager
from .constants import CLICK_STYLE
from .exceptions import (
    ConfigurationError,
    IncantError,
    InstanceError,
    ProjectError,
    ProvisioningError,
)
from .incus_cli import IncusCLI
from .instance_manager import InstanceManager
from .project_manager import ProjectManager
from .provisioning_manager import ProvisioningManager
from .types import CliOptions, IncantConfig, InstanceName, ProjectName


class Incant:
    """
    Main Incant application class that coordinates all operations.

    This class acts as a facade/coordinator for the various managers
    that handle specific aspects of the application.
    """

    def __init__(self, **kwargs):
        # Store options and initialize managers
        self.options: CliOptions = kwargs
        self.verbose = kwargs.get("verbose", False)
        self.quiet = kwargs.get("quiet", False)

        # Initialize configuration manager
        self.config_manager = ConfigurationManager(self.options)

        # Load configuration
        self.config_data: Optional[IncantConfig] = None
        if not kwargs.get("no_config", False):
            self.config_data = self._load_and_validate_config()

        # Initialize other managers
        self.incus = IncusCLI()
        self.project_manager = ProjectManager(self.incus, self.config_manager, verbose=self.verbose)
        self.instance_manager = InstanceManager(self.incus, verbose=self.verbose)
        self.provisioning_manager = ProvisioningManager(self.incus, verbose=self.verbose)

    def _load_and_validate_config(self) -> Optional[IncantConfig]:
        """Load and validate configuration, handling errors gracefully."""
        try:
            config = self.config_manager.load_config()
            if config:
                self.config_manager.validate_config(config)
            return config
        except ConfigurationError as e:
            if not self.quiet:
                click.secho(str(e), **CLICK_STYLE["error"])
            return None

    def _ensure_config_loaded(self) -> IncantConfig:
        """Ensure configuration is loaded and valid."""
        if not self.config_data:
            click.secho("No valid configuration available.", **CLICK_STYLE["error"])
            sys.exit(1)
        return self.config_data

    def _handle_error(self, error: Exception, operation: str) -> None:
        """Handle errors consistently across operations."""
        if isinstance(error, IncantError):
            click.secho(f"Error during {operation}: {error}", **CLICK_STYLE["error"])
        else:
            click.secho(f"Unexpected error during {operation}: {error}", **CLICK_STYLE["error"])
        sys.exit(1)

    def dump_config(self) -> None:
        """Dump the loaded configuration to stdout."""
        try:
            if not self.config_data:
                click.secho("No configuration loaded to dump.", **CLICK_STYLE["error"])
                sys.exit(1)

            self.config_manager.dump_config(self.config_data)

        except ConfigurationError as e:
            self._handle_error(e, "dump config")

    def up(self, name: Optional[InstanceName] = None) -> None:
        """Start and provision instances."""
        config = self._ensure_config_loaded()

        try:
            # Validate instance name if provided
            if name and name not in config["instances"]:
                raise InstanceError(f"Instance '{name}' not found in config")

            # Set up project if needed
            project_name = self.project_manager.setup_project_if_needed(config)

            # Update incus CLI to use the project
            if project_name:
                self.incus.project = project_name
                self.instance_manager.incus.project = project_name
                self.provisioning_manager.incus.project = project_name

            # Step 1: Create all instances (they boot in parallel)
            instances_config = config["instances"]
            created_instances = self.instance_manager.create_instances(instances_config, name)

            # Step 2: Set up shared folders and provision
            self.instance_manager.setup_shared_folders(instances_config, name)

            # Step 3: Auto-provision instances that have provision: true
            self._auto_provision_instances(instances_config, name)

        except (InstanceError, ProjectError, ProvisioningError) as e:
            self._handle_error(e, "up")

    def _auto_provision_instances(
        self, instances_config: dict, target_instance: Optional[InstanceName] = None
    ) -> None:
        """Automatically provision instances that have provision configured."""
        instances_to_check = {}
        if target_instance:
            instances_to_check[target_instance] = instances_config[target_instance]
        else:
            instances_to_check = instances_config

        for instance_name, instance_data in instances_to_check.items():
            if instance_data.get("provision"):
                self.provisioning_manager.provision_instance(instance_name, instance_data)

    def provision(self, name: Optional[InstanceName] = None) -> None:
        """Provision instances."""
        config = self._ensure_config_loaded()

        try:
            # Set up project if needed
            project_name = self.project_manager.setup_project_if_needed(config)

            # Update incus CLI to use the project
            if project_name:
                self.incus.project = project_name
                self.provisioning_manager.incus.project = project_name

            # Provision instances
            instances_config = config["instances"]
            self.provisioning_manager.provision_instances(instances_config, name)

        except (ProjectError, ProvisioningError) as e:
            self._handle_error(e, "provision")

    def destroy(self, name: Optional[InstanceName] = None) -> None:
        """Destroy instances and clean up projects if needed."""
        config = self._ensure_config_loaded()

        try:
            # Validate instance name if provided
            if name and name not in config["instances"]:
                raise InstanceError(f"Instance '{name}' not found in config")

            # Set up project if needed (to get project name)
            project_name = self.project_manager.setup_project_if_needed(config)

            # Update incus CLI to use the project
            if project_name:
                self.incus.project = project_name
                self.instance_manager.incus.project = project_name

            # Destroy instances
            instances_config = config["instances"]
            destroyed_instances = self.instance_manager.destroy_instances(instances_config, name)

            # Handle project cleanup
            self._handle_project_cleanup(project_name, name, destroyed_instances)

        except (InstanceError, ProjectError) as e:
            self._handle_error(e, "destroy")

    def _handle_project_cleanup(
        self,
        project_name: Optional[ProjectName],
        target_instance: Optional[InstanceName],
        destroyed_instances: list,
    ) -> None:
        """Handle project cleanup after destroying instances."""
        if not project_name:
            return

        if target_instance is None:  # Destroying all instances
            if destroyed_instances:
                click.secho(
                    f"Destroyed {len(destroyed_instances)} instance(s).", **CLICK_STYLE["info"]
                )
            else:
                click.secho("No instances found to destroy.", **CLICK_STYLE["info"])

            # Always try to clean up the project when destroying all instances
            self.project_manager.cleanup_project_if_needed(project_name)

        elif destroyed_instances:  # Destroyed a specific instance
            # Check if this was the last instance in the project
            remaining_instances = self.incus.list_instances_in_project(project_name)
            if not remaining_instances:
                self.project_manager.cleanup_project_if_needed(project_name)

    def list_instances(self) -> None:
        """List all instances defined in the configuration."""
        config = self._ensure_config_loaded()

        try:
            for instance_name in config["instances"]:
                click.echo(instance_name)
        except Exception as e:
            self._handle_error(e, "list")

    def incant_init(self) -> None:
        """Create an example configuration file."""
        try:
            self.config_manager.create_example_config()
        except ConfigurationError as e:
            self._handle_error(e, "init")
