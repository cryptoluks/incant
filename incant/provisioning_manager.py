"""
Provisioning management for Incant.
"""

from typing import Dict, List, Union

import click

from .constants import CLICK_STYLE
from .exceptions import ProvisioningError
from .types import InstanceName, InstanceDefinition, ProvisionStep


class ProvisioningManager:
    """Handles provisioning of instances."""

    def __init__(self, incus_cli, verbose: bool = False):
        self.incus = incus_cli
        self.verbose = verbose

    def provision_instance(
        self, instance_name: InstanceName, instance_data: InstanceDefinition
    ) -> None:
        """Provision a single instance based on its configuration."""
        provisions = instance_data.get("provision", [])

        if not provisions:
            if self.verbose:
                click.secho(f"No provisioning found for {instance_name}.", **CLICK_STYLE["info"])
            return

        click.secho(f"Provisioning instance {instance_name}...", **CLICK_STYLE["success"])

        try:
            # Handle different provision step formats
            if isinstance(provisions, str):
                self._execute_provision_step(instance_name, provisions)
            elif isinstance(provisions, list):
                for step in provisions:
                    click.secho("Running provisioning step ...", **CLICK_STYLE["info"])
                    self._execute_provision_step(instance_name, step)
            else:
                raise ProvisioningError(f"Invalid provision format for {instance_name}")

        except Exception as e:
            raise ProvisioningError(f"Failed to provision {instance_name}: {e}")

    def _execute_provision_step(self, instance_name: InstanceName, step: ProvisionStep) -> None:
        """Execute a single provisioning step."""
        try:
            self.incus.provision(instance_name, step, quiet=not self.verbose)
        except Exception as e:
            raise ProvisioningError(f"Provision step failed for {instance_name}: {e}")

    def provision_instances(
        self,
        instances_config: Dict[InstanceName, InstanceDefinition],
        target_instance: InstanceName = None,
    ) -> None:
        """Provision multiple instances or a specific instance."""
        if target_instance:
            # Provision only the specified instance
            if target_instance not in instances_config:
                raise ProvisioningError(f"Instance '{target_instance}' not found in config")

            self.provision_instance(target_instance, instances_config[target_instance])
        else:
            # Provision all instances that have provisioning configured
            for instance_name, instance_data in instances_config.items():
                if instance_data.get("provision"):
                    self.provision_instance(instance_name, instance_data)
