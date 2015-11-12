"""Various utils."""

import os
from functools import reduce

root_path = os.path.dirname(os.path.realpath(__file__))


def t_path(filename="."):
    """Get the path of the test file inside test directory."""
    return os.path.join(root_path, filename)


def list_files(startpath):
    """tree unix command replacement."""
    s = u'\n'
    for root, dirs, files in os.walk(startpath):
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * level
        s += u'{}{}/\n'.format(indent, os.path.basename(root))
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            s += u'{}{}\n'.format(subindent, f)
    return s


def file_tree(startpath):
    """
    Create a nested dictionary that represents the folder structure of rootdir.

    Liberally adapted from
    http://code.activestate.com/recipes/577879-create-a-nested-dictionary-from-oswalk/
    """
    dir = {}
    rootdir = startpath.rstrip(os.sep)
    start = rootdir.rfind(os.sep) + 1
    for path, dirs, files in os.walk(rootdir):
        folders = path[start:].split(os.sep)
        subdir = dict.fromkeys(files)
        parent = reduce(dict.get, folders[:-1], dir)
        parent[folders[-1]] = subdir
    return dir
