"""
Project management for Incant.
"""

import re
from pathlib import Path
from typing import Optional

import click

from .constants import CLICK_STYLE
from .exceptions import ProjectError
from .types import ProjectName, IncantConfig


def sanitize_name(name: str) -> str:
    """Sanitize a name to be suitable for use as a project name.

    Converts to lowercase and replaces non-alphanumeric characters with hyphens.
    This is useful for converting directory names to valid project names.
    """
    return re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")


class ProjectManager:
    """Handles project isolation and lifecycle management."""

    def __init__(self, incus_cli, config_manager, verbose: bool = False):
        self.incus = incus_cli
        self.config_manager = config_manager
        self.verbose = verbose

    def get_project_name_from_config(self, config: IncantConfig) -> Optional[ProjectName]:
        """Get the project name if project isolation is enabled."""
        if not config or not config.get("project", False):
            return None

        config_file = self.config_manager.find_config_file()
        if config_file is None:
            raise ProjectError("Cannot determine parent directory for project name.")

        parent_dir_name = config_file.parent.name
        project_name = sanitize_name(parent_dir_name)

        if not project_name:
            raise ProjectError("Cannot create valid project name from parent directory.")

        return project_name

    def setup_project_if_needed(self, config: IncantConfig) -> Optional[ProjectName]:
        """Sets up project isolation if project: true is specified in config."""
        project_name = self.get_project_name_from_config(config)
        if not project_name:
            return None

        # Check if project already exists
        if not self.incus.project_exists(project_name):
            if self.verbose:
                click.secho(
                    f"Creating project '{project_name}'...",
                    **CLICK_STYLE["info"],
                )

            try:
                # Create project with shared images by default
                project_config = {
                    "features.images": "false"  # Allow access to default project's images
                }
                self.incus.create_project(project_name, config=project_config)

                # Copy default profile from default project to new project
                if self.verbose:
                    click.secho(
                        f"Copying default profile to project '{project_name}'...",
                        **CLICK_STYLE["info"],
                    )
                self.incus.copy_default_profile_to_project(project_name)

                click.secho(
                    f"Created project '{project_name}' with shared images.",
                    **CLICK_STYLE["success"],
                )
            except Exception as e:
                raise ProjectError(f"Failed to create project '{project_name}': {e}")
        else:
            if self.verbose:
                click.secho(f"Project '{project_name}' already exists.", **CLICK_STYLE["info"])

        return project_name

    def cleanup_project_if_needed(self, project_name: ProjectName) -> None:
        """Cleans up project if it's empty and was created by incant."""
        if not project_name:
            return

        try:
            # Check if project has any instances left
            instances = self.incus.list_instances_in_project(project_name)
            if not instances:
                if self.verbose:
                    click.secho(
                        f"Project '{project_name}' is empty, deleting it...", **CLICK_STYLE["info"]
                    )
                self.incus.delete_project(project_name, quiet=not self.verbose)
                click.secho(f"Deleted empty project '{project_name}'.", **CLICK_STYLE["success"])
        except Exception as e:
            if self.verbose:
                click.secho(
                    f"Warning: Could not clean up project '{project_name}': {e}",
                    **CLICK_STYLE["warning"],
                )
