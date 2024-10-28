from typing import Any, Optional

import click

from infernet_cli.cli.docker import (
<<<<<<< HEAD
    destroy_services,
    docker_destroy,
    docker_start,
    docker_stop,
    health_check,
=======
    destroy_containers,
    destroy_service,
    health_check,
    start_service,
    stop_service,
>>>>>>> 0d634d74 (fix: arewave impl)
)
from infernet_cli.node import get_configs
from infernet_cli.service import add_service_container, remove_service_container

from .options import (
    config_inputs_option,
    config_skip_option,
    deploy_dir_option,
<<<<<<< HEAD
    destroy_services_option,
=======
    destroy_containers_option,
>>>>>>> 0d634d74 (fix: arewave impl)
)


@click.group()
def cli() -> None:
    pass


@config_skip_option
@click.option(
    "-y",
    "--yes",
    is_flag=True,
    help="Force overwrite of existing configurations.",
)
@config_inputs_option
@click.option(
    "--gpu",
    is_flag=True,
    default=False,
    help="Enable GPU support for the node.",
)
@deploy_dir_option
@click.option(
    "-v",
    "--version",
    type=str,
    required=False,
    help="The version of the node to configure.",
)
@click.argument(
    "chain",
    type=click.Choice(
        ["anvil", "base", "base-sepolia", "eth", "other"], case_sensitive=False
    ),
    required=True,
)
@cli.command(
    "config",
    help="Pull node configurations.",
)
def config(
    chain: str,
    version: str,
    dir: str,
    gpu: bool,
    inputs: Optional[dict[str, Any]] = None,
    yes: bool = False,
    skip: bool = False,
) -> None:
    """Pull node configurations for a specific chain."""

    get_configs(chain, dir, gpu, version, inputs, force=yes, skip=skip)


@deploy_dir_option
<<<<<<< HEAD
@cli.command("start", help="Start the Infernet Node.")
def start(dir: str) -> None:
    click.echo("Starting Infernet Node...")
    docker_start(dir)


@deploy_dir_option
@cli.command("health", help="Check health of the Infernet Node.")
def health(dir: str) -> None:
=======
@cli.command("start", help="Start Docker services.")
def start(dir: str) -> None:
    """Start the services using docker-compose."""

    click.echo("Starting Docker services...")
    start_service(dir)


@deploy_dir_option
@cli.command("health", help="Check the health of Docker services.")
def health(dir: str) -> None:
    """Check the health of the services."""

>>>>>>> 0d634d74 (fix: arewave impl)
    health_check(dir)


@deploy_dir_option
<<<<<<< HEAD
@cli.command("stop", help="Stop the Infernet Node.")
def stop(dir: str) -> None:
    click.echo("Stopping Infernet Node...")
    docker_stop(dir)
=======
@cli.command("stop", help="Stop Docker services.")
def stop(dir: str) -> None:
    """Stop services."""

    click.echo("Stopping Docker services...")
    stop_service(dir)
>>>>>>> 0d634d74 (fix: arewave impl)


def abort_if_false(ctx: Any, param: Any, value: Optional[str]) -> None:
    if not value:
        click.Abort()


<<<<<<< HEAD
=======
@destroy_containers_option
>>>>>>> 0d634d74 (fix: arewave impl)
@click.option(
    "-y",
    "--yes",
    is_flag=True,
    callback=abort_if_false,
    expose_value=False,
<<<<<<< HEAD
    help="No manual y/n confirmation required.",
    prompt="Are you sure you want to destroy the Infernet Node?",
)
@destroy_services_option
@deploy_dir_option
@cli.command("destroy", help="Destroy the Infernet Node.")
def destroy(dir: str, services: bool = False) -> None:
    click.echo("Destroying Infernet Node...")
    docker_stop(dir)
    docker_destroy(dir)

    if services:
        click.echo("Destroying service containers...")
        destroy_services(dir)


@destroy_services_option
@deploy_dir_option
@cli.command("reset", help="Reset Infernet Node.")
def reset(dir: str, services: bool = False) -> None:
    click.echo("Resetting Infernet Node...")
    docker_stop(dir)

    if services:
        click.echo("Destroying service containers...")
        destroy_services(dir)

    docker_start(dir)
=======
    prompt="Are you sure you want to remove all services?",
)
@deploy_dir_option
@cli.command("destroy", help="Remove Docker services.")
def destroy(dir: str, containers: bool = False) -> None:
    """Destroy services."""

    click.echo("Destroying services...")
    stop_service(dir)
    destroy_service(dir)

    if containers:
        click.echo("Destroying containers...")
        destroy_containers(dir)


@destroy_containers_option
@deploy_dir_option
@cli.command("reset", help="Reset Docker services.")
def reset(dir: str, containers: bool = False) -> None:
    """Reset services."""

    click.echo("Resetting Docker services...")
    stop_service(dir)

    if containers:
        click.echo("Destroying containers...")
        destroy_containers(dir)

    start_service(dir)
>>>>>>> 0d634d74 (fix: arewave impl)


@config_skip_option
@config_inputs_option
@deploy_dir_option
@click.argument("recipe_id", type=str, required=False)
@cli.command(
    "add-service",
<<<<<<< HEAD
    help="Add a service to the node configuration.",
=======
    help="Configure a service for the node.",
>>>>>>> 0d634d74 (fix: arewave impl)
)
def add_service(
    recipe_id: Optional[str],
    dir: str,
    inputs: Optional[dict[str, Any]] = None,
    skip: bool = False,
) -> None:
<<<<<<< HEAD
=======
    """Add container configuration to the node config.json."""

>>>>>>> 0d634d74 (fix: arewave impl)
    add_service_container(recipe_id, dir, inputs, skip)


@deploy_dir_option
@click.argument("service_id", type=str, required=False)
@cli.command(
    "remove-service",
<<<<<<< HEAD
    help="Remove a service from the node configuration.",
)
def remove_service(service_id: Optional[str], dir: str) -> None:
=======
    help="Remove a service from the node.",
)
def remove_service(service_id: Optional[str], dir: str) -> None:
    """Remove a service from the node."""

>>>>>>> 0d634d74 (fix: arewave impl)
    remove_service_container(service_id, dir)
