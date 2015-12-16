#! /usr/bin/env python3

# sftpclone can be imported into a custom Python script to deploy a
# static website to a web host where you only have stripped-down sftp
# access. The below is an example of a deployment script that keeps
# your username and password out of the shell history and uses an
# exclude file. In practice, one might have complex needs. For
# example, the website may be built from assets in multiple,
# separately managed directory trees on the local host. Using
# sftpclone programmatically with exclude files makes it easy to
# script one-step deployments for such situations.

import getpass
import os
from sftpclone import sftpclone

def get_username_and_password():
    username = input("Username [{}]: ".format(getpass.getuser()))
    if not username:
        username = getpass.getuser()

    password = getpass.getpass()

    return (username, password)

def deploy_assets(username, password):
    # The local path and the remote path in this function should
    # correspond to where you build the static site locally and where
    # it should go on the remote sftp server.
    cloner = sftpclone.SFTPClone(
        './build',
        "{}:{}@mysite.example.com:./mysite".format(username, password),
        exclude_file = 'exclude.txt'
    )
    cloner.run()

if __name__ == "__main__":
    username, password = get_username_and_password()
    deploy_assets(username, password)
