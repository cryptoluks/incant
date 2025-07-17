import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import click

from .constants import CLICK_STYLE
from .exceptions import IncusCommandError, ProjectError, InstanceError
from .types import ProjectName, InstanceName, CommandList


class CommandBuilder:
    """Helper class to build Incus commands."""

    @staticmethod
    def build_launch_command(
        image: str,
        name: str,
        vm: bool = False,
        profiles: Optional[List[str]] = None,
        config: Optional[Dict[str, str]] = None,
        devices: Optional[Dict[str, Dict[str, str]]] = None,
        network: Optional[str] = None,
        instance_type: Optional[str] = None,
    ) -> CommandList:
        """Build a launch command with all parameters."""
        command = ["launch", image, name]

        if vm:
            command.append("--vm")

        if profiles:
            for profile in profiles:
                command.extend(["--profile", profile])

        if config:
            for key, value in config.items():
                command.extend(["--config", f"{key}={value}"])

        if devices:
            for dev_name, dev_attrs in devices.items():
                dev_str = f"{dev_name}"
                for k, v in dev_attrs.items():
                    dev_str += f",{k}={v}"
                command.extend(["--device", dev_str])

        if network:
            command.extend(["--network", network])

        if instance_type:
            command.extend(["--type", instance_type])

        return command


class IncusCLI:
    """
    Improved Python wrapper for the Incus CLI interface.
    """

    def __init__(self, incus_cmd: str = "incus", project: str = None):
        self.incus_cmd = incus_cmd
        self.project = project

    def _run_command(
        self,
        command: CommandList,
        *,
        capture_output: bool = True,
        allow_failure: bool = False,
        exception_on_failure: bool = False,
        quiet: bool = True,
        project: str = None,
    ) -> str:
        """Execute an Incus CLI command with improved error handling."""
        full_command = self._build_full_command(command, project)

        if not quiet:
            click.secho(f"-> {' '.join(full_command)}", **CLICK_STYLE["info"])

        try:
            result = subprocess.run(
                full_command, capture_output=capture_output, text=True, check=True
            )
            return result.stdout

        except subprocess.CalledProcessError as e:
            error_message = f"Failed: {e.stderr.strip()}" if capture_output else "Command failed"

            if allow_failure:
                if not quiet:
                    click.secho(error_message, **CLICK_STYLE["error"])
                return ""
            elif exception_on_failure:
                raise IncusCommandError(
                    error_message,
                    command=" ".join(full_command),
                    stderr=e.stderr if capture_output else None,
                )
            else:
                click.secho(error_message, **CLICK_STYLE["error"])
                raise IncusCommandError(error_message, command=" ".join(full_command))

    def _build_full_command(self, command: CommandList, project: str = None) -> CommandList:
        """Build the full command with project flags if needed."""
        full_command = [self.incus_cmd]

        # Handle project specification
        active_project = project if project != "none" else None
        if active_project is None and project != "none":
            active_project = self.project

        if active_project and active_project != "default":
            full_command.extend(["--project", active_project])

        full_command.extend(command)
        return full_command

    # Instance operations
    def create_instance(
        self,
        name: str,
        image: str,
        profiles: Optional[List[str]] = None,
        vm: bool = False,
        config: Optional[Dict[str, str]] = None,
        devices: Optional[Dict[str, Dict[str, str]]] = None,
        network: Optional[str] = None,
        instance_type: Optional[str] = None,
    ) -> None:
        """Create a new instance with optional parameters."""
        command = CommandBuilder.build_launch_command(
            image, name, vm, profiles, config, devices, network, instance_type
        )
        self._run_command(command)

    def destroy_instance(self, name: str) -> None:
        """Destroy (stop if needed, then delete) an instance."""
        self._run_command(["delete", "--force", name], allow_failure=True)

    def is_instance(self, name: str) -> bool:
        """Check if an instance exists."""
        try:
            self.get_instance_info(name)
            return True
        except IncusCommandError:
            return False

    def get_instance_info(self, name: str) -> Dict:
        """Get detailed information about an instance."""
        current_project = self.project or self.get_current_project()
        output = self._run_command(
            ["query", f"/1.0/instances/{name}?project={current_project}&recursion=1"],
            quiet=True,
            exception_on_failure=True,
            project="none",
        )
        return json.loads(output)

    def is_instance_stopped(self, name: str) -> bool:
        """Check if an instance is stopped."""
        return self.get_instance_info(name)["status"] == "Stopped"

    def is_agent_running(self, name: str) -> bool:
        """Check if the instance agent is running."""
        return self.get_instance_info(name).get("state", {}).get("processes", -2) > 0

    def is_agent_usable(self, name: str) -> bool:
        """Check if the instance agent is usable."""
        try:
            self.exec(name, ["true"], exception_on_failure=True, quiet=True)
            return True
        except IncusCommandError as e:
            if e.stderr and "VM agent isn't currently running" in e.stderr:
                return False
            raise

    def is_instance_booted(self, name: str) -> bool:
        """Check if the instance has fully booted."""
        try:
            self.exec(name, ["which", "systemctl"], quiet=True, exception_on_failure=True)
        except IncusCommandError:
            # No systemctl in instance. We assume it booted
            raise InstanceError("systemctl not found in instance")

        try:
            systemctl = self.exec(
                name,
                ["systemctl", "is-system-running"],
                quiet=True,
                exception_on_failure=True,
            ).strip()
        except IncusCommandError:
            return False

        return systemctl == "running"

    def is_instance_ready(self, name: str, verbose: bool = False) -> bool:
        """Check if an instance is completely ready."""
        if not self.is_agent_running(name):
            return False

        if verbose:
            click.secho("Agent is running, testing if usable...", **CLICK_STYLE["info"])

        if not self.is_agent_usable(name):
            return False

        if verbose:
            click.secho("Agent is usable, checking if system booted...", **CLICK_STYLE["info"])

        if not self.is_instance_booted(name):
            return False

        return True

    def exec(self, name: str, command: CommandList, cwd: str = None, **kwargs) -> str:
        """Execute a command in an instance."""
        cmd = ["exec"]
        if cwd:
            cmd.extend(["--cwd", cwd])
        cmd.extend([name, "--"] + command)
        return self._run_command(cmd, **kwargs)

    # Shared folder operations
    def create_shared_folder(self, name: str) -> None:
        """Create a shared folder for an instance with retry logic."""
        curdir = Path.cwd()
        base_command = [
            "config",
            "device",
            "add",
            name,
            f"{name}_shared_incant",
            "disk",
            f"source={curdir}",
            "path=/incant",
        ]

        # First attempt with shift enabled
        command = base_command + ["shift=true"]

        try:
            self._run_command(command, exception_on_failure=True, capture_output=False)
        except IncusCommandError:
            click.secho(
                "Shared folder creation failed. Retrying without shift=true...",
                **CLICK_STYLE["warning"],
            )
            # Retry without shift
            self._run_command(base_command, capture_output=False)

        # Verify shared folder creation with retries
        self._verify_shared_folder_with_retries(name)

    def _verify_shared_folder_with_retries(self, name: str, max_attempts: int = 10) -> None:
        """Verify shared folder creation with retry logic."""
        for attempt in range(max_attempts):
            try:
                self.exec(
                    name,
                    ["grep", "-wq", "/incant", "/proc/mounts"],
                    exception_on_failure=True,
                    capture_output=False,
                )
                return  # Success

            except IncusCommandError:
                click.secho(
                    "Shared folder creation failed (/incant not mounted). Retrying...",
                    **CLICK_STYLE["warning"],
                )
                # Clean up and retry
                self._run_command(
                    ["config", "device", "remove", name, f"{name}_shared_incant"],
                    capture_output=False,
                    allow_failure=True,
                )
                curdir = Path.cwd()
                self._run_command(
                    [
                        "config",
                        "device",
                        "add",
                        name,
                        f"{name}_shared_incant",
                        "disk",
                        f"source={curdir}",
                        "path=/incant",
                    ],
                    capture_output=False,
                )

        raise InstanceError("Shared folder creation failed after all retries")

    # Project operations
    def create_project(self, name: str) -> None:
        """Create a new project."""
        try:
            self._run_command(["project", "create", name], project="none")
        except IncusCommandError as e:
            raise ProjectError(f"Failed to create project {name}: {e}")

    def delete_project(self, name: str, quiet: bool) -> None:
        """Delete a project with proper error handling."""
        try:
            process = subprocess.run(
                [self.incus_cmd, "project", "delete", "--force", name],
                input="yes\n",
                text=True,
                capture_output=True,
            )

            if process.returncode == 0:
                if not quiet:
                    click.secho(
                        f"-> {self.incus_cmd} project delete --force {name}", **CLICK_STYLE["info"]
                    )
            else:
                if not quiet:
                    click.secho(
                        f"Note: Could not delete project {name}: {process.stderr.strip()}",
                        **CLICK_STYLE["warning"],
                    )

        except Exception as e:
            if not quiet:
                click.secho(
                    f"Warning: Could not delete project {name}: {e}", **CLICK_STYLE["warning"]
                )

    def project_exists(self, name: str) -> bool:
        """Check if a project exists."""
        projects = self.list_projects()
        return name in projects

    def list_projects(self) -> List[str]:
        """List all available projects."""
        try:
            output = self._run_command(
                ["project", "list", "--format=csv"], quiet=True, project="none"
            )
            return self._parse_csv_output(output)
        except IncusCommandError:
            return []

    def get_current_project(self) -> str:
        """Get the current project name."""
        return self._run_command(["project", "get-current"], quiet=True, project="none").strip()

    def copy_default_profile_to_project(self, project_name: str) -> None:
        """Copy the default profile from the default project to the specified project."""
        try:
            # Get default profile from default project
            profile_content = self._run_command(
                ["profile", "show", "default"], quiet=True, project="default"
            )

            # Apply it to the target project
            process = subprocess.run(
                [self.incus_cmd, "--project", project_name, "profile", "edit", "default"],
                input=profile_content,
                text=True,
                capture_output=True,
            )

            if process.returncode != 0:
                click.secho(
                    f"Warning: Could not copy default profile to project {project_name}: {process.stderr}",
                    **CLICK_STYLE["warning"],
                )

        except IncusCommandError as e:
            click.secho(
                f"Warning: Could not copy default profile to project {project_name}: {e}",
                **CLICK_STYLE["warning"],
            )

    def list_instances_in_project(self, project_name: str = None) -> List[str]:
        """List all instances in the specified project."""
        try:
            output = self._run_command(
                ["list", "--format=csv"], quiet=True, project=project_name or self.project
            )
            return self._parse_csv_output(output)
        except IncusCommandError:
            return []

    def _parse_csv_output(self, output: str) -> List[str]:
        """Parse CSV output and return the first column (names)."""
        lines = output.strip().split("\n")
        if len(lines) <= 1:  # Header only or empty
            return []

        items = []
        for line in lines[1:]:  # Skip header
            if line.strip():
                # First column contains the name (may have suffixes)
                name = line.split(",")[0].strip('"').split(" ")[0]
                items.append(name)
        return items

    # Provisioning operations
    def provision(self, name: str, provision: str, quiet: bool) -> None:
        """Provision an instance with a single command or multi-line script."""
        if "\n" not in provision:  # Single-line command
            self.exec(
                name,
                ["sh", "-c", provision],
                quiet=quiet,
                capture_output=False,
                cwd="/incant",
            )
        else:  # Multi-line script
            self._provision_with_script(name, provision, quiet)

    def _provision_with_script(self, name: str, provision: str, quiet: bool) -> None:
        """Provision an instance with a multi-line script."""
        fd, temp_path = tempfile.mkstemp(prefix="incant_")

        try:
            # Write the script content to the temporary file
            with os.fdopen(fd, "w") as temp_file:
                temp_file.write(provision)

            # Get just the filename and deploy to /tmp
            temp_filename = os.path.basename(temp_path)
            target_path = f"/tmp/{temp_filename}"

            # Copy the file to the instance
            self._run_command(["file", "push", temp_path, f"{name}{target_path}"], quiet=quiet)

            # Execute the script after copying
            self.exec(
                name,
                ["sh", "-c", f"chmod +x {target_path} && {target_path} && rm {target_path}"],
                quiet=quiet,
                capture_output=False,
            )
        finally:
            # Clean up the local temporary file
            if os.path.exists(temp_path):
                os.remove(temp_path)
