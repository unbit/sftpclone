#!/usr/bin/env python
# coding=utf-8

"""Various test utils."""

import logging
import os
import sys

from contextlib import contextmanager
from functools import reduce

try:  # Python < 3
    from StringIO import StringIO
except ImportError:
    from io import StringIO

root_path = os.path.dirname(os.path.realpath(__file__))


def t_path(filename="."):
    """Get the path of the test file inside test directory."""
    return os.path.join(root_path, filename)


def list_files(start_path):
    """tree unix command replacement."""
    s = u'\n'
    for root, dirs, files in os.walk(start_path):
        level = root.replace(start_path, '').count(os.sep)
        indent = ' ' * 4 * level
        s += u'{}{}/\n'.format(indent, os.path.basename(root))
        sub_indent = ' ' * 4 * (level + 1)
        for f in files:
            s += u'{}{}\n'.format(sub_indent, f)
    return s


def file_tree(start_path):
    """
    Create a nested dictionary that represents the folder structure of `start_path`.

    Liberally adapted from
    http://code.activestate.com/recipes/577879-create-a-nested-dictionary-from-oswalk/
    """
    nested_dirs = {}
    root_dir = start_path.rstrip(os.sep)
    start = root_dir.rfind(os.sep) + 1
    for path, dirs, files in os.walk(root_dir):
        folders = path[start:].split(os.sep)
        subdir = dict.fromkeys(files)
        parent = reduce(dict.get, folders[:-1], nested_dirs)
        parent[folders[-1]] = subdir
    return nested_dirs


@contextmanager
def capture_sys_output():
    """Capture standard output and error."""
    capture_out, capture_err = StringIO(), StringIO()
    current_out, current_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = capture_out, capture_err
        yield capture_out, capture_err
    finally:
        sys.stdout, sys.stderr = current_out, current_err


@contextmanager
def suppress_logging(log_level=logging.CRITICAL):
    """Suppress logging."""
    logging.disable(log_level)
    yield
    logging.disable(logging.NOTSET)


@contextmanager
def override_env_variables():
    """Override user environmental variables with custom one."""
    env_vars = ("LOGNAME", "USER", "LNAME", "USERNAME")
    old = [os.environ[v] if v in os.environ else None for v in env_vars]

    for v in env_vars:
        os.environ[v] = "test"
    yield

    for i, v in enumerate(env_vars):
        if old[i]:
            os.environ[v] = old[i]


@contextmanager
def override_ssh_auth_env():
    """Override the `$SSH_AUTH_SOCK `env variable to mock the absence of an SSH agent."""
    ssh_auth_sock = "SSH_AUTH_SOCK"
    old_ssh_auth_sock = os.environ.get(ssh_auth_sock)

    del os.environ[ssh_auth_sock]

    yield

    if old_ssh_auth_sock:
        os.environ[ssh_auth_sock] = old_ssh_auth_sock


