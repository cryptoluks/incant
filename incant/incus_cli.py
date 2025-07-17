import subprocess
import json
from typing import List, Dict, Optional
import sys
import tempfile
import os
from pathlib import Path
import click

# click output styles
CLICK_STYLE = {
    "success": {"fg": "green", "bold": True},
    "info": {"fg": "cyan"},
    "warning": {"fg": "yellow"},
    "error": {"fg": "red"},
}


class IncusCLI:
    """
    A Python wrapper for the Incus CLI interface.
    """

    def __init__(self, incus_cmd: str = "incus", project: str = None):
        self.incus_cmd = incus_cmd
        self.project = project

    def _run_command(
        self,
        command: List[str],
        *,
        capture_output: bool = True,
        allow_failure: bool = False,
        exception_on_failure: bool = False,
        quiet: bool = False,
        project: str = None,
    ) -> str:
        """Executes an Incus CLI command and returns the output. Optionally allows failure."""
        try:
            full_command = [self.incus_cmd] + command

            # Add project flag if specified (either from method param or instance setting)
            # Special case: project="none" means don't add any project flag
            active_project = project if project != "none" else None
            if active_project is None and project != "none":
                active_project = self.project

            if active_project and active_project != "default":
                # Insert --project flag before the command
                full_command = [self.incus_cmd, "--project", active_project] + command

            if not quiet:
                click.secho(f"-> {' '.join(full_command)}", **CLICK_STYLE["info"])
            result = subprocess.run(
                full_command, capture_output=capture_output, text=True, check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            error_message = f"Failed: {e.stderr.strip()}" if capture_output else "Command failed"
            if allow_failure:
                click.secho(error_message, **CLICK_STYLE["error"])
                return ""
            elif exception_on_failure:
                raise
            else:
                click.secho(error_message, **CLICK_STYLE["error"])
                sys.exit(1)

    def exec(self, name: str, command: List[str], cwd: str = None, **kwargs) -> str:
        cmd = ["exec"]
        if cwd:
            cmd.extend(["--cwd", cwd])
        cmd.extend([name, "--"] + command)
        return self._run_command(cmd, **kwargs)

    def create_project(self, name: str) -> None:
        """Creates a new project."""
        command = ["project", "create", name]
        self._run_command(
            command, project="none"
        )  # Always use default context for project management

    def delete_project(self, name: str, quiet: bool = False) -> None:
        """Deletes a project."""
        try:
            # Use subprocess directly to handle the interactive prompt
            # We need to provide "yes" as input to confirm the deletion
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
                # Project might not exist or other error - this is usually fine
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

    def switch_project(self, name: str) -> None:
        """Switches to a specific project."""
        command = ["project", "switch", name]
        self._run_command(
            command, project="none"
        )  # Always use default context for project management

    def list_projects(self) -> list:
        """Lists all available projects."""
        output = self._run_command(["project", "list", "--format=csv"], quiet=True, project="none")
        # Parse CSV output and return project names
        lines = output.strip().split("\n")
        if len(lines) <= 1:  # Header only or empty
            return []
        projects = []
        for line in lines[1:]:  # Skip header
            if line.strip():
                # First column is the project name (may have " (current)" suffix)
                project_name = line.split(",")[0].strip('"').split(" ")[0]
                projects.append(project_name)
        return projects

    def project_exists(self, name: str) -> bool:
        """Checks if a project exists."""
        projects = self.list_projects()
        return name in projects

    def copy_default_profile_to_project(self, project_name: str) -> None:
        """Copies the default profile from the default project to the specified project."""
        try:
            # Get default profile from default project
            profile_content = self._run_command(
                ["profile", "show", "default"], quiet=True, project="default"
            )

            # Apply it to the target project (this will create/update the default profile)
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

        except subprocess.CalledProcessError as e:
            click.secho(
                f"Warning: Could not copy default profile to project {project_name}: {e}",
                **CLICK_STYLE["warning"],
            )

    def list_instances_in_project(self, project_name: str = None) -> list:
        """Lists all instances in the specified project."""
        try:
            output = self._run_command(
                ["list", "--format=csv"], quiet=True, project=project_name or self.project
            )
            lines = output.strip().split("\n")
            if len(lines) <= 1:  # Header only or empty
                return []
            instances = []
            for line in lines[1:]:  # Skip header
                if line.strip():
                    # First column is the instance name
                    instance_name = line.split(",")[0].strip('"')
                    instances.append(instance_name)
            return instances
        except subprocess.CalledProcessError:
            return []

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
        """Creates a new instance with optional parameters."""
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

        self._run_command(command)

    def create_shared_folder(self, name: str) -> None:
        curdir = Path.cwd()
        command = [
            "config",
            "device",
            "add",
            name,
            f"{name}_shared_incant",
            "disk",
            f"source={curdir}",
            "path=/incant",
            "shift=true",  # First attempt with shift enabled
        ]

        try:
            self._run_command(command, exception_on_failure=True, capture_output=False)
        except subprocess.CalledProcessError:
            click.secho(
                "Shared folder creation failed. Retrying without shift=true...",
                **CLICK_STYLE["warning"],
            )
            command.remove("shift=true")  # Remove shift option and retry
            self._run_command(command, capture_output=False)

        # Sometimes the creation of shared directories fails (see https://github.com/lxc/incus/issues/1881)
        # So we retry up to 10 times
        for attempt in range(10):
            try:
                self.exec(
                    name,
                    ["grep", "-wq", "/incant", "/proc/mounts"],
                    exception_on_failure=True,
                    capture_output=False,
                )
                return True
            except subprocess.CalledProcessError:
                click.secho(
                    "Shared folder creation failed (/incant not mounted). Retrying...",
                    **CLICK_STYLE["warning"],
                )
                self._run_command(
                    ["config", "device", "remove", name, f"{name}_shared_incant"],
                    capture_output=False,
                )
                self._run_command(command, capture_output=False)

        raise Exception("Shared folder creation failed.")

    def destroy_instance(self, name: str) -> None:
        """Destroy (stop if needed, then delete) an instance."""
        self._run_command(["delete", "--force", name], allow_failure=True)

    def get_current_project(self) -> str:
        return self._run_command(["project", "get-current"], quiet=True, project="none").strip()

    def get_instance_info(self, name: str) -> Dict:
        """Gets detailed information about an instance."""
        current_project = self.project or self.get_current_project()
        # For API queries, we include project in URL and don't use --project flag
        output = self._run_command(
            [
                "query",
                f"/1.0/instances/{name}?project={current_project}&recursion=1",
            ],
            quiet=True,
            exception_on_failure=True,
            project="none",  # Special value to prevent adding --project flag
        )
        return json.loads(output)

    def is_instance_stopped(self, name: str) -> bool:
        return self.get_instance_info(name)["status"] == "Stopped"

    def is_agent_running(self, name: str) -> bool:
        return self.get_instance_info(name).get("state", {}).get("processes", -2) > 0

    def is_agent_usable(self, name: str) -> bool:
        try:
            self.exec(name, ["true"], exception_on_failure=True, quiet=True)
            return True
        except subprocess.CalledProcessError as e:
            if e.stderr.strip() == "Error: VM agent isn't currently running":
                return False
            else:
                raise

    def is_instance_booted(self, name: str) -> bool:
        try:
            self.exec(name, ["which", "systemctl"], quiet=True, exception_on_failure=True)
        except Exception as exc:
            # no systemctl in instance. We assume it booted
            # return True
            raise RuntimeError("systemctl not found in instance") from exc
        try:
            systemctl = self.exec(
                name,
                ["systemctl", "is-system-running"],
                quiet=True,
                exception_on_failure=True,
            ).strip()
        except subprocess.CalledProcessError:
            return False
        return systemctl == "running"

    def is_instance_ready(self, name: str, verbose: bool = False) -> bool:
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

    def is_instance(self, name: str) -> bool:
        """Checks if an instance exists."""
        try:
            self.get_instance_info(name)
            return True
        except subprocess.CalledProcessError:
            return False

    def provision(self, name: str, provision: str, quiet: bool = True) -> None:
        """Provision an instance with a single command or a multi-line script."""

        if "\n" not in provision:  # Single-line command
            # Change to /incant and then execute the provision command inside
            # sh -c for quoting safety
            self.exec(
                name,
                ["sh", "-c", provision],
                quiet=quiet,
                capture_output=False,
                cwd="/incant",
            )
        else:  # Multi-line script
            # Create a secure temporary file locally
            fd, temp_path = tempfile.mkstemp(prefix="incant_")

            try:
                # Write the script content to the temporary file
                with os.fdopen(fd, "w") as temp_file:
                    temp_file.write(provision)

                # Copy the file to the instance
                self._run_command(["file", "push", temp_path, f"{name}{temp_path}"], quiet=quiet)

                # Execute the script after copying
                self.exec(
                    name,
                    [
                        "sh",
                        "-c",
                        f"chmod +x {temp_path} && {temp_path} && rm {temp_path}",
                    ],
                    quiet=quiet,
                    capture_output=False,
                )
            finally:
                # Clean up the local temporary file
                os.remove(temp_path)
