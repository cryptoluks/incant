"""
Instance management for Incant.
"""

import time
from typing import Dict, List, Optional

import click

from .constants import CLICK_STYLE
from .exceptions import InstanceError
from .types import InstanceName, InstanceDefinition


class InstanceManager:
    """Handles instance lifecycle management."""

    def __init__(self, incus_cli, verbose: bool = False):
        self.incus = incus_cli
        self.verbose = verbose

    def create_instance(
        self, instance_name: InstanceName, instance_data: InstanceDefinition
    ) -> None:
        """Create a single instance based on its configuration."""
        image = instance_data.get("image")
        if not image:
            raise InstanceError(f"Instance {instance_name}: No image defined")

        # Check if instance already exists
        if self.incus.is_instance(instance_name):
            if self.verbose:
                click.secho(
                    f"Instance {instance_name} already exists, skipping creation.",
                    **CLICK_STYLE["info"],
                )
            return

        # Extract instance configuration
        vm = instance_data.get("vm", False)
        profiles = instance_data.get("profiles", None)
        config = instance_data.get("config", None)
        devices = instance_data.get("devices", None)
        network = instance_data.get("network", None)
        instance_type = instance_data.get("type", None)

        click.secho(
            f"Creating instance {instance_name} with image {image}...",
            **CLICK_STYLE["success"],
        )

        try:
            self.incus.create_instance(
                instance_name,
                image,
                profiles=profiles,
                vm=vm,
                config=config,
                devices=devices,
                network=network,
                instance_type=instance_type,
            )
        except Exception as e:
            raise InstanceError(f"Failed to create instance {instance_name}: {e}")

    def setup_shared_folder(
        self, instance_name: InstanceName, instance_data: InstanceDefinition
    ) -> None:
        """Set up shared folder for an instance."""
        try:
            # Wait for the agent to become ready before sharing the current directory
            self._wait_for_agent(instance_name)

            click.secho(
                f"Sharing current directory to {instance_name}:/incant ...",
                **CLICK_STYLE["success"],
            )

            # Wait for the instance to become ready if specified in config, or
            # we want to perform provisioning, or the instance is a VM
            should_wait = (
                instance_data.get("wait", False)
                or instance_data.get("provision", False)
                or instance_data.get("vm", False)
            )

            if should_wait:
                self._wait_for_instance_ready(instance_name)

            self.incus.create_shared_folder(instance_name)

        except Exception as e:
            raise InstanceError(f"Failed to setup shared folder for {instance_name}: {e}")

    def _wait_for_agent(self, instance_name: InstanceName) -> None:
        """Wait for the instance agent to become ready."""
        while True:
            if self.incus.is_agent_running(instance_name) and self.incus.is_agent_usable(
                instance_name
            ):
                break
            time.sleep(0.3)

    def _wait_for_instance_ready(self, instance_name: InstanceName) -> None:
        """Wait for the instance to become fully ready."""
        click.secho(
            f"Waiting for {instance_name} to become ready...",
            **CLICK_STYLE["info"],
        )
        while True:
            if self.incus.is_instance_ready(instance_name, True):
                click.secho(
                    f"Instance {instance_name} is ready.",
                    **CLICK_STYLE["success"],
                )
                break
            time.sleep(1)

    def destroy_instance(self, instance_name: InstanceName) -> bool:
        """Destroy a single instance."""
        if not self.incus.is_instance(instance_name):
            if self.verbose:
                click.secho(f"Instance '{instance_name}' does not exist.", **CLICK_STYLE["info"])
            return False

        click.secho(f"Destroying instance {instance_name} ...", **CLICK_STYLE["success"])

        try:
            self.incus.destroy_instance(instance_name)
            return True
        except Exception as e:
            raise InstanceError(f"Failed to destroy instance {instance_name}: {e}")

    def create_instances(
        self,
        instances_config: Dict[InstanceName, InstanceDefinition],
        target_instance: InstanceName = None,
    ) -> List[InstanceName]:
        """Create multiple instances or a specific instance."""
        created_instances = []

        # Filter instances based on target
        instances_to_create = {}
        if target_instance:
            if target_instance not in instances_config:
                raise InstanceError(f"Instance '{target_instance}' not found in config")
            instances_to_create[target_instance] = instances_config[target_instance]
        else:
            instances_to_create = instances_config

        # Create instances in parallel (they boot in parallel)
        for instance_name, instance_data in instances_to_create.items():
            try:
                self.create_instance(instance_name, instance_data)
                created_instances.append(instance_name)
            except InstanceError as e:
                click.secho(f"Skipping {instance_name}: {e}", **CLICK_STYLE["error"])

        return created_instances

    def setup_shared_folders(
        self,
        instances_config: Dict[InstanceName, InstanceDefinition],
        target_instance: InstanceName = None,
    ) -> None:
        """Set up shared folders for instances."""
        instances_to_setup = {}
        if target_instance:
            if target_instance not in instances_config:
                raise InstanceError(f"Instance '{target_instance}' not found in config")
            instances_to_setup[target_instance] = instances_config[target_instance]
        else:
            instances_to_setup = instances_config

        for instance_name, instance_data in instances_to_setup.items():
            # Only setup shared folder if instance exists
            if self.incus.is_instance(instance_name):
                self.setup_shared_folder(instance_name, instance_data)

    def destroy_instances(
        self,
        instances_config: Dict[InstanceName, InstanceDefinition],
        target_instance: InstanceName = None,
    ) -> List[InstanceName]:
        """Destroy multiple instances or a specific instance."""
        destroyed_instances = []

        # Filter instances based on target
        instances_to_destroy = {}
        if target_instance:
            if target_instance not in instances_config:
                raise InstanceError(f"Instance '{target_instance}' not found in config")
            instances_to_destroy[target_instance] = instances_config[target_instance]
        else:
            instances_to_destroy = instances_config

        for instance_name in instances_to_destroy:
            if self.destroy_instance(instance_name):
                destroyed_instances.append(instance_name)

        return destroyed_instances
