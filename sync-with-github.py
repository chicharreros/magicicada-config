from __future__ import unicode_literals

import json
import os
import shutil
import subprocess
import sys

from tempfile import mkdtemp

import tweepy


PROJECTS = [
    'lp:magicicada-server',
    'lp:magicicada-protocol',
    'lp:magicicada-client',
    'lp:magicicada-gui',
]
NOTHING_TO_LAND = 'No approved proposals found for %s'

# The path to your lp:tarmac branch (bzr branch lp:tarmac)
TARMAC_HOME = os.path.abspath(
    os.environ.get('TARMAC_HOME', '/var/cache/tarmac'))
assert os.path.isdir(TARMAC_HOME), '%s should be a valid folder' % TARMAC_HOME

# The path to a folder containing the clones of the 4 magicicada projects:
# mkdir ~/tmp/magicicada
# cd ~/tmp/magicicada
# git clone git@github.com:chicharreros/magicicada-server.git
# git clone git@github.com:chicharreros/magicicada-protocol.git
# git clone git@github.com:chicharreros/magicicada-client.git
# git clone git@github.com:chicharreros/magicicada-gui.git
MAGICICADA_GH_HOME = os.path.abspath(os.environ.get('MAGICICADA_GH_HOME', '.'))
for i in PROJECTS:
    path = os.path.join(MAGICICADA_GH_HOME, i.replace('lp:', '', 1))
    assert os.path.isdir(path), '%s should be a valid folder' % path

# The path to a file with your twitter credentials to advertise the commits
TWITTER_AUTH_JSON = os.path.abspath(
    os.environ.get('TWITTER_AUTH_JSON', 'auth.json'))
assert os.path.isfile(TWITTER_AUTH_JSON), (
    '%s should be a valid file' % TWITTER_AUTH_JSON)


def tweet(msg, dry_run=False):
    allowed_len = 140
    msg = msg.rpartition(']')[-1].strip()
    if len(msg) > allowed_len:
        msg = msg[:allowed_len - 3] + '...'
    print('\n\n---------------- TWEETTING %s -------------------' % len(msg))
    print(msg)
    print('\n\n')
    if dry_run:
        return
    with open(TWITTER_AUTH_JSON) as f:
        oauth_creds = json.loads(f.read)
    auth = tweepy.OAuthHandler(
        oauth_creds['consumer_token'], oauth_creds['consumer_secret'])
    auth.set_access_token(
        oauth_creds['access_token'], oauth_creds['access_secret'])
    api = tweepy.API(auth)
    api.update_status(status=msg)


def check_output(cmd, dry_run=False, **kwargs):
    # kwargs.setdefault('stderr', subprocess.STDOUT)
    cmd_line = cmd
    if isinstance(cmd, list):
        cmd_line = ' '.join(cmd)
    result = ''
    if not dry_run:
        result = str(subprocess.check_output(cmd, **kwargs))
    else:
        print('++ Executing:', cmd_line, kwargs)
        print('++ Result:', result)
    return result


def parse_bzr_commit_log(dry_run=True):
    lines = check_output(['bzr', 'log', '-l1', project], dry_run=dry_run)
    data = {}
    for line in lines.replace(':\n', ':').split('\n'):
        if ':' not in line:
            continue
        k, v = line.split(':', 1)
        data[k] = v.strip()
    author = data['author']
    name, email = author.rsplit(' ', 1)
    data['name'] = name
    data['email'] = email.strip('<>')
    return data


def main(project, force=False, dry_run=False):
    target = project.replace('lp:', '')
    github_clone_path = os.path.join(MAGICICADA_GH_HOME, target)
    assert os.path.isdir(github_clone_path), (
        '%s is not a valid folder' % github_clone_path)
    source = mkdtemp()

    tarmac_merge = [
        os.path.join(TARMAC_HOME, 'bin', 'tarmac'),
        'merge', '--debug', project]
    landing = check_output(
        tarmac_merge, dry_run=dry_run, stderr=subprocess.STDOUT,
        env={'PYTHONPATH': TARMAC_HOME})
    if NOTHING_TO_LAND % project in landing and not force:
        print(NOTHING_TO_LAND % project)
        return

    commit_data = parse_bzr_commit_log(dry_run=dry_run)
    check_output(['bzr', 'export', source, project], dry_run=dry_run)
    try:
        # source folder needs to end with /, otherwise rsync will sync the
        # folder itself instead its contents.
        check_output(
            "rsync --delete -zvrh --exclude='.git/' %s/ %s" %
            (source.rstrip('/'), github_clone_path), shell=True,
            dry_run=dry_run)
        os.chdir(github_clone_path)
        check_output(['git', 'add', '*'], dry_run=dry_run)
        env = {'GIT_COMMITTER_NAME': commit_data['name'],
               'GIT_COMMITTER_EMAIL': commit_data['email']}
        check_output(['git', 'commit', '-a', '-m', commit_data['message'],
                      '--author="%s"' % commit_data['author']], dry_run=dry_run,
                     env=env)
        check_output(['git', 'push', 'origin', 'master'], dry_run=dry_run)
    finally:
        shutil.rmtree(source)

    if force:
        return  # early exit, do not tweet.

    # tweet
    msg = 'Commit in %s: %s' % (
        target.replace('magicicada-', ''), commit_data['message'])
    tweet(msg, dry_run=dry_run)


if __name__ == '__main__':
    try:
        project = sys.argv[1]
    except IndexError:
        project = None
    else:
        assert project in PROJECTS

    try:
        force = bool(sys.argv[2])
    except IndexError:
        force = False

    dry_run = False
    if project is None:
        for p in PROJECTS:
            main(project=p, dry_run=dry_run)
    else:
        main(project=project, force=force, dry_run=dry_run)
