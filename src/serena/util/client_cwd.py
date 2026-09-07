"""
Detection of the working directory of the MCP client process (e.g. Claude Code).

Clients like Claude Code can change the working directory of their own process during a session
(e.g. when entering a git worktree). Since the MCP server process is not restarted in that case,
reading the client's working directory is the only way for Serena to notice the change.
"""

import os
from functools import cache

import psutil
from sensai.util import logging

log = logging.getLogger(__name__)

DEFAULT_CLIENT_PROCESS_NAMES = ("claude", "claude.exe")
"""names of client processes whose working directory is meaningful for project selection"""

_MAX_ANCESTOR_DEPTH = 12
"""maximum number of ancestors to inspect when searching for the client process"""


@cache
def _client_process_names() -> tuple[str, ...]:
    """
    :return: the lower-case process names to look for when identifying the client process,
        overridable via the environment variable `SERENA_CLIENT_PROCESS_NAMES` (comma-separated)
    """
    configured = os.environ.get("SERENA_CLIENT_PROCESS_NAMES")
    if not configured:
        return DEFAULT_CLIENT_PROCESS_NAMES
    names = tuple(name.strip().lower() for name in configured.split(",") if name.strip())
    return names or DEFAULT_CLIENT_PROCESS_NAMES


def find_client_process() -> psutil.Process | None:
    """
    Searches the chain of ancestor processes for the MCP client process.

    The client is not necessarily the direct parent: depending on how the server is launched,
    there can be intermediate processes (e.g. `uv`, a shell, `cmd.exe`).

    :return: the client process or None if it could not be identified
    """
    names = _client_process_names()
    try:
        process: psutil.Process | None = psutil.Process(os.getpid())
    except psutil.Error as e:
        log.debug("Could not access own process: %s", e)
        return None

    for _ in range(_MAX_ANCESTOR_DEPTH):
        try:
            assert process is not None
            process = process.parent()
        except psutil.Error as e:
            log.debug("Could not access parent process: %s", e)
            return None
        if process is None:
            return None
        try:
            if process.name().lower() in names:
                return process
        except psutil.Error as e:
            log.debug("Could not read process name: %s", e)
            return None
    return None


def get_client_working_directory() -> str | None:
    """
    Determines the current working directory of the MCP client process.

    :return: the absolute path of the client's working directory or None if it could not be determined
        (e.g. because the client process was not found or the platform denies access)
    """
    process = find_client_process()
    if process is None:
        return None
    try:
        return process.cwd()
    except psutil.Error as e:
        # on some platforms/permission setups, reading the cwd of another process is not permitted
        log.debug("Could not read working directory of client process: %s", e)
        return None
