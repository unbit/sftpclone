"""Various utils."""

import os

root_path = os.path.dirname(os.path.realpath(__file__))


def t_path(filename="."):
	"""Get the path of the test file inside test directory."""
	return os.path.join(root_path, filename)


def list_files(startpath):
	"""tree unix command replacement."""
	for root, dirs, files in os.walk(startpath):
		level = root.replace(startpath, '').count(os.sep)
		indent = ' ' * 4 * (level)
		print('{}{}/'.format(indent, os.path.basename(root)))
		subindent = ' ' * 4 * (level + 1)
		for f in files:
			print('{}{}'.format(subindent, f))
