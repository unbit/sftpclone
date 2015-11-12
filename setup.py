"""Setup configuration file."""

from setuptools import setup


def readme():
	"""Open the readme."""
	with open('README.md') as f:
		return f.read()

setup(
	name='sftpclone',
	version='1.1',
	description='A tool for cloning/syncing a local directory tree with an SFTP server',
	long_description=readme(),
	url='https://github.com/unbit/sftpclone',

	author='Adriano Di Luzio',
	author_email='adrianodl@hotmail.it',

	packages=['sftpclone'],
	install_requires=[
		'paramiko',
	],
	test_suite='nose.collector',
	tests_require=['nose'],
	scripts=['bin/sftpclone'],

	keywords=["sftpclone", "sftp", "sync", "ftp", "ssh"],
	license='MIT',
	classifiers=[
		"Programming Language :: Python",
		"Programming Language :: Python :: 3",
		"Development Status :: 6 - Mature",
		"Environment :: Other Environment",
		"Intended Audience :: Developers",
		"Intended Audience :: End Users/Desktop",
		"Intended Audience :: Information Technology",
		"License :: OSI Approved :: MIT License",
		"Operating System :: OS Independent",
		"Topic :: System :: Archiving :: Backup",
		"Topic :: System :: Archiving :: Mirroring",
		"Topic :: Internet :: File Transfer Protocol (FTP)",
		"Topic :: Utilities"
	],

	zip_safe=False,
	include_package_data=True,
)
