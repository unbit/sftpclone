# sftpclone

[![PyPI version](https://img.shields.io/pypi/v/sftpclone.svg?style=flat-square)](https://pypi.python.org/pypi/sftpclone)
![PyPI python version](https://img.shields.io/pypi/pyversions/sftpclone.svg?style=flat-square)
[![PyPI license](https://img.shields.io/pypi/l/sftpclone.svg?style=flat-square)](LICENSE)

A tool for cloning/syncing a local directory tree with an SFTP server.

## Features

* Keep in sync a local directory tree with a specified folder of an SFTP server.
* Update symbolic links as needed and keep files _consistent_.
* Automatic tilde expansion/handling on the SFTP server.
* Public key authentication.
* `ssh_config` entries compatibility.
* Syncing exclusion patterns.
* Compatible with both Python 2 and Python 3.

## Install
You can install sftpclone by using pip:

```bash
$ pip install sftpclone --user
```

**Note**: Sometimes building required dependencies in user mode doesn't work. In that case, you'd need to use `sudo` and to remove the `--user` flag.
Alternatively, you could make use of a virtualenv.

Alternatively, you can clone this repository and then launch:

```bash
$ git clone https://github.com/unbit/sftpclone
$ cd sftpclone
$ python setup.py install
```

In both cases, you'll find the sftpclone script in your path.

## Usage

```
usage: sftpclone [-h] [-k private-key-path]
                 [-l {CRITICAL,ERROR,WARNING,INFO,DEBUG,NOTSET}] [-p PORT]
                 [-f] [-a] [-c ssh config path] [-n known_hosts path] [-d]
                 [-e exclude-from-file-path] [-t] [-o]
                 local-path user[:password]@hostname:remote-path
```

Where, for each command line argument:

* **local-path**: The path of the local folder. This path must exists and can contain `~` (we use tilde expansion).
* **sftp-url**: It specifies the remote SFTP url having the form: `[user[:password]@]hostname:remote-path`. Both the password and the user field can be omitted. If you omit the former then you should specify a private key identity file. If you omit the latter then the current user is automatically used. The hostname can refer to a element of your `ssh_config` file. If the remote path contains `~`, then it will be expanded to the default folder in which the user begins her SFTP session.
* **[h]elp**: show the help message and exit.
* **private-[k]ey-path**: the path to your private identity file. Set it if you are not using password authentication. It automatically defaults to `~/.ssh/id_rsa` and can be used more than once.
* **[l]ogging**: set the log level (ERROR by default).
* **[p]ort**: SSH remote port (defaults to 22).
* **[f]ix-symlinks**: if you have absolute symlinks pointing to your synced directory, they will remain consistent on the remote server: i.e., they will have an absolute path that reflect the path of the cloned directory on the server. Useful for cluster configurations.
* **ssh-[a]gent**: enable ssh-agent support. Any private-[k]ey-path argument will be ignored.
* **ssh-[c]onfig-path**: in the sftp-url's hostname you can [specify an entry of your `ssh_config` file](#ssh_config-compatibility). If you are using a non-standard path, you can set it here.
* **k[n]own_hosts path**: path to your [`known_hosts`](#known_hosts-checking) file. Default to `~/.ssh/known_hosts`.
* **[d]isable-known-hosts**: [disable remote fingerprint](#known_hosts-checking) check against local `known_host` file.
* **[e]xclude-from-file-path**: the path to a file containing a list of patterns. Each file matched by these pattern [will be ignored](#exclude-list) (not synced).
* **do-not-dele[t]e**: do not delete remote files that are missing from the local directory.
* **all[o]w-unknown**: do not ask for confirmation before connecting to unknown hosts.

**Warning**: be sure to select a __proper__ remote folder. 
The synchronization process will indeed delete any file that doesn't exist in the local folder (unless you turn the `-t` option on).

## `ssh_config` compatibility

The hostname in the sftp-url parameter can be a valid entry in a `ssh_config` file. Specifically, your entry should have relevant parameters such as:

* `HostName`
* `User`
* `Port`
* `IdentityFile`
* `ProxyCommand`

Any value not found will fallback to the CLI arguments. 
Anyway, you _have to set_ the `IdentityFile` field, otherwise authentication will try to fallback to `~/.ssh/id_rsa` and could not work.
The first hostname matching the pattern is chosen (in the `ssh_config` way).

## `known_hosts` checking

By default sftpclone will match the remote host fingerprint against the one contained in your `~/.ssh/known_hosts` file.
If this file doesn't exists on your machine, you can specify a different path by using the `-n` option.
Furthermore, you can disable the check with the `-d` flag.
Unknown hosts will require the user to authorize the connection. Please note that, even after authorization, the `known_host`
file won't be modified.

## Exclude list

It takes inspiration from the rsync/tar `--exclude-from` flag.

You can specify among your command line arguments a file containing a list of patterns, one per each line.
All those files that match any pattern will not be synced with the SFTP server.

Lines beginning with `;` or `#` are ignored.

Each pattern is considered relative to the syncing directory. As a consequence, leading `/` are ignored.

### Example

```ini
; This will exclude any file or directory beginning with foo
foo*
; This will exclude any file foo in a subdir of the directory bar.
bar/*/foo
```

## Programmatic usage

You can find some examples of programmatic usage inside the [examples](examples) directory.

## Testing

This project uses [nose](https://nose.readthedocs.org/en/latest/) for testing.
In addition, on Python 2 you'll need the `mock` module (part of Python standard lib from 3.3).
In both cases, you can install test requirements with:

```bash
$ pip install -r test_requirements.txt
```

Then, You can launch the test suite by using, from the project root directory:
```bash
$ nosetests
$ python setup.py test # alternatively
```
