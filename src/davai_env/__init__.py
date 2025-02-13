#!/usr/bin/env python3
# -*- coding:Utf-8 -*-
"""
Davai environment around experiments and shelves.
"""
from __future__ import print_function, absolute_import, unicode_literals, division

import os
import re
import configparser
import socket
import io
import copy
import subprocess
import datetime

package_rootdir = os.path.dirname(os.path.dirname(os.path.realpath(__path__[0])))  # realpath to resolve symlinks
__version__ = io.open(os.path.join(package_rootdir, 'VERSION'), 'r').read().strip()

# fixed parameters
davai_rc = os.path.join(os.environ['HOME'], '.davairc')
davai_profile = os.path.join(davai_rc, 'profile')
davai_xp_counter = os.path.join(os.environ['HOME'], '.davairc', '.last_xp')
davai_xpid_syntax = 'dv-{xpid_num:04}-{host}@{user}'
davai_xpid_re = re.compile('^' + davai_xpid_syntax.replace('{xpid_num:04}', '\d+').
                                                   replace('-{host}', '(-\w+)?').
                                                   replace('{user}', '\w+') + '$')

# repo
this_repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


def expandpath(path):
    return os.path.expanduser(os.path.expandvars(path))


def guess_host():
    """
    Guess host from (by order of resolution):
      - presence as 'host' in section [hosts] of base and user config
      - resolution from socket.gethostname() through RE patterns of base and user config
    """
    host = config.get('hosts', 'host', fallback=None)
    if not host:
        socket_hostname = socket.gethostname()
        for h, pattern in config['hosts'].items():
            if re.match(pattern, socket_hostname):
                host = h[:-len('_re_pattern')]  # h is '{host}_re_pattern'
                break
    if not host:
        raise ValueError(("Couldn't find 'host' in [hosts] section of config files ('{}', '{}'), " +
                          "nor guess from hostname ({}) and keys '*host*_re_pattern' " +
                          "in section 'hosts' of same config files.").format(
            user_config_file, base_config_file, socket_hostname))
    return host

# config
base_config_file = os.path.join(this_repo, 'conf', 'base.ini')
user_config_file = os.path.join(davai_rc, 'user_config.ini')
config = configparser.ConfigParser()
config.read(base_config_file)
# read user config a first time to help guessing host
if os.path.exists(user_config_file):
    config.read(user_config_file)
# then complete config with host config file
host_config_file = os.path.join(this_repo, 'conf', '{}.ini'.format(guess_host()))
if os.path.exists(host_config_file):
    config.read(host_config_file)
# and read again user config so that it overwrites host config
if os.path.exists(user_config_file):
    config.read(user_config_file)
DAVAI_TESTS_REPO = expandpath(config.get('paths', 'davai_tests_repo'))


def next_xp_num():
    """Get number of next Experiment."""
    if not os.path.exists(davai_xp_counter):
        num = 0
    else:
        with open(davai_xp_counter, 'r') as f:
            num = int(f.readline())
    next_num = num + 1
    with open(davai_xp_counter, 'w') as f:
        f.write(str(next_num))
    return next_num


def init(token=None):
    """
    Initialize Davai env for user.
    """
    # Setup home
    print("Setup DAVAI home directory ({}) ...".format(config.get('paths', 'davai_home')))
    for d in ('davai_home', 'experiments', 'logs', 'mtooldir'):
        p = expandpath(config.get('paths', d))
        if os.path.exists(p):
            if not os.path.isdir(p):
                raise ValueError("config[paths][{}] is not a directory : '{}'".format(d, p))
        else:
            if '$' in p:
                raise ValueError("config[paths][{}] is not expandable : '{}'".format(d, p))
            os.makedirs(p)
    # tests repo
    if not os.path.exists(DAVAI_TESTS_REPO):
        print("Clone DAVAI-tests repository into '{}'...".format(DAVAI_TESTS_REPO))
        subprocess.check_call(['git', 'clone', config.get('defaults', 'davai_tests_origin')],
                              cwd=os.path.dirname(DAVAI_TESTS_REPO))
    # set rc
    print("Setup {} ...".format(davai_rc))
    if not os.path.exists(davai_rc):
        os.makedirs(davai_rc)
    # link bin (to have command line tools in PATH)
    link = os.path.join(davai_rc, 'bin')
    this_repo_bin = os.path.join(this_repo, 'bin')
    if os.path.islink(link) or os.path.exists(link):
        if os.path.islink(link) and os.readlink(link) == this_repo_bin:
            link = False
        else:
            overwrite = input("Relink '{}' to '{}' ? (y/n) : ".format(link, this_repo_bin)) in ('y', 'Y')
            if overwrite:
                os.unlink(link)
            else:
                link = None
            print("Warning: initialization might not be consistent with existing link !")
    if link:
        os.symlink(this_repo_bin, link)
        export_path = "export PATH=$PATH:{}\n".format(link)
        with io.open(davai_profile, 'a') as p:
            p.write(export_path)
    # token
    if token:
        export_token_in_profile(token)
    # profile
    bash_profile = os.path.join(os.environ['HOME'], '.bash_profile')
    with io.open(bash_profile, 'r') as b:
        sourced = any([davai_profile in l for l in b.readlines()])
    if not sourced:
        source = ['# DAVAI profile\n',
                  'if [ -f {} ]; then\n'.format(davai_profile),
                  '. {}\n'.format(davai_profile),
                  'fi\n',
                  '\n']
        with io.open(bash_profile, 'a') as b:
            b.writelines(source)
    print("------------------------------")
    print("DAVAI initialization completed. Re-login or source {} to finalize.".format(davai_profile))


def update(pull=False, token=None):
    """Update DAVAI-env and DAVAI-tests repositories using `git fetch`."""
    print("Update repo {} ...".format(DAVAI_TESTS_REPO))
    subprocess.check_call(['git', 'fetch', 'origin'], cwd=DAVAI_TESTS_REPO)
    print("Update repo {} ...".format(this_repo))
    subprocess.check_call(['git', 'fetch', 'origin'], cwd=this_repo)
    if pull:
        subprocess.check_call(['git', 'pull', 'origin'], cwd=this_repo)
    if token:
        export_token_in_profile(token)


def default_mtooldir():
    MTOOLDIR = expandpath(config['paths'].get('mtooldir'))
    return MTOOLDIR


def export_token_in_profile(token):
    with io.open(davai_profile, 'a') as p:
        p.write("export CIBOULAI_TOKEN={}  # update: {}\n".format(token, str(datetime.date.today())))

