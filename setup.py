#!/usr/bin/env python
# coding=utf-8
"""Setup configuration file."""

import setuptools


def readme():
    """Try converting the README to an RST document. Return it as is on failure."""
    with open('README.md') as f:
        return f.read()


setuptools.setup(
    name='sftpclone',
    version='1.2.2',

    description='A tool for cloning/syncing a local directory tree with an SFTP server.',

    long_description=readme(),
    long_description_content_type="text/markdown",

    url='https://github.com/unbit/sftpclone',

    author='Adriano Di Luzio',
    author_email='adrianodl@hotmail.it',

    packages=setuptools.find_packages(),

    install_requires=['paramiko==2.4.1', ],
    test_suite='nose.collector',
    tests_require=['nose', 'mock', ],
    scripts=['bin/sftpclone', ],

    keywords=["sftpclone", "sftp", "sync", "ftp", "ssh", ],
    license='MIT',
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
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
