"""Setup configuration file."""

from setuptools import setup


def readme():
    """Try converting the README to an RST document. Return it as is on failure."""
    try:
        import pypandoc
        readme = pypandoc.convert('README.md', 'rst')
    except(IOError, ImportError):
        print("Warning: no pypandoc module found.")
        try:
            readme = open('README.md').read()
        except IOError:
            readme = ''
    return readme


setup(
    name='sftpclone',
    version='1.1.2',
    description='A tool for cloning/syncing a local directory tree with an SFTP server.',
    long_description=readme(),
    url='https://github.com/unbit/sftpclone',

    author='Adriano Di Luzio',
    author_email='adrianodl@hotmail.it',

    packages=['sftpclone'],
    install_requires=['paramiko', ],
    test_suite='nose.collector',
    tests_require=['nose', ],
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
