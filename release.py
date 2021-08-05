#!/usr/bin/python3

#
# Step interactively through the release process for osbuild
#

import argparse
import subprocess, sys
import os
import getpass
from re import search
import requests

# FIXME: Somehow these colors don't do what they should yet...
class fg:
    BOLD = '\033[1m' # bold
    OK = '\033[32m' # green
    WARNING = '\033[33m' # yellow
    ERROR = '\033[31m' # red
    RESET = '\033[0m' # reset

def msg_error(body):
    print(f"{fg.ERROR}{fg.BOLD}Error:{fg.RESET} {body}")
    sys.exit(1)

def msg_info(body):
    print(f"{fg.WARNING}{fg.BOLD}Info:{fg.RESET} {body}")

def msg_ok(body):
    print(f"{fg.OK}{fg.BOLD}OK:{fg.RESET} {body}")

# Check if we are in a git repo, on the right branch and up-to-date
def sanity_checks():
    is_git = run_command(['git', 'rev-parse', '--is-inside-work-tree'])
    if  is_git != "true":
        msg_error("This is not a git repository.")

    current_branch = run_command(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    if current_branch.__contains__("release"):
        msg_info(f"You are already on a release branch: {current_branch}")
    elif current_branch != "main":
        msg_error(f"You are not on the 'main' branch but on branch '{current_branch}'.")

    is_clean = run_command(['git', 'status', '--untracked-files=no', '--porcelain'])
    if is_clean != "":
        status = run_command(['git', 'status', '--untracked-files=no', '-s'])
        msg_info("The working directory is not clean.\n"
                 "You have the following unstaged or uncommitted changes:\n"
                 f"{status}")
    return current_branch

# Run a shellcommand and return stdout
def run_command(argv):
    result = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8').stdout
    return result.strip()

# Ask the user for confirmation on whether to accept (y) or skip (s) the step or cancel (N) the playbook
def step(action, args):
    feedback = input(f"{action} [y/s/N] ")
    if feedback == "y":
        out = run_command(args)
        msg_ok (out)
    elif feedback == "s":
        msg_info("Step skipped.")
        return
    else:
        msg_info("Release playbook canceled.")
        sys.exit(0)

# Bump the version of the latest git tag by 1
def autoincrement_version():
    latest_tag = run_command(['git', 'describe', '--abbrev=0'])
    version = int(latest_tag.replace("v","")) + 1
    return version

# Guess the git remote to push the release changes to
def guess_remote(repo):
    origin = f"github.com[/:]osbuild/{repo}.git"
    remotes = run_command(['git','remote']).split("\n")
    if len(remotes) > 2:
        msg_info("You have more than two 'git remotes' specified, so guessing the correct one will most likely fail.\n"
                 "Please use the --remote argument to set the correct one.\n"
                 f"{remotes}")

    for remote in remotes:
        remote_url = run_command(['git','remote','get-url',f'{remote}'])
        if search(origin, remote_url) is None:
            return remote

def create_pullrequest(args, repo):
    if args.user is None or args.token is None:
        msg_error("Missing credentials for GitHub.")

    msg_info(f"Creating a pull request on github for user {args.user}")
    url = f'https://api.github.com/repos/osbuild/{repo}/pulls'
    payload = {'head':f'{args.user}:release-{args.version}',
               'base':'main',
               'title':f'Prepare release {args.version}',
               'body':'Tasks:\n- Bump version\n-Update news',
              }

    r = requests.post(url, json = payload, auth=(args.user,args.token))
    try:
        msg_ok(f"Pull request successfully created: {r.json()['url']}")
    except:
        msg_error(f"Failed to create pull request. {r.json()}")

# Execute all steps of the release playbook
def release_playbook(args, repo):
    step(f"Check out a new branch for the release {args.version}", ['git', 'checkout', '-b', f'release-{args.version}'])
    step("Generate template for new release", ['make', 'release'])
    step(f"Bump the version to {args.version}", ['make', 'bump-version'])
    step(f"Please make sure the version was bumped correctly to {args.version}", ['git', 'diff'])
    # TODO: Call the pr_summaries.py script for osbuild or assemble the news from docs/news/unreleased for composer
    step(f"Add and commit the release-relevant changes ({repo}.spec NEWS.md setup.py)",
          ['git', 'commit', f'{repo}.spec', 'NEWS.md', 'setup.py', '-s', f'-m {args.version}', f'-m "Release osbuild {args.version}"'])
    step(f"Push all release changes to the remote '{args.remote}'",
          ['git', 'push', '--set-upstream', f'{args.remote}', f'release-{args.version}'])
    create_pullrequest(args, repo)

def main():
    # Do some initial sanity checking of the repository and its state
    current_branch = sanity_checks()

    # Get some basic fallback/default values
    repo = os.path.basename(os.getcwd())
    version = autoincrement_version()
    remote = guess_remote(repo)
    username = getpass.getuser()

    parser = argparse.ArgumentParser()
    parser.add_argument("--version", help=f"Set the version for the release (Default: {version})", default=version)
    parser.add_argument("--remote", help=f"Set the git remote on github to push the release changes to (Default: {remote})", default=remote)
    parser.add_argument("--user", help=f"Set the username on github (Default: {username})", default=username)
    parser.add_argument("--token", help="Set the github token used to authenticate")
    args = parser.parse_args()

    msg_info(f"Updating branch '{current_branch}' to avoid conflicts...\n{run_command(['git', 'pull'])}")

    # Run the release playbook
    release_playbook(args, repo)


if __name__ == "__main__":
    main()
