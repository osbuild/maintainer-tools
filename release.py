#!/usr/bin/python3

#
# Step interactively through the release process for osbuild
#

import argparse
import subprocess, sys
import os
import getpass
from re import search

# Check if we are in a git repo, on the right branch and up-to-date
def sanity_checks():
    is_git = run_command(['git', 'rev-parse', '--is-inside-work-tree'])
    if  is_git != "true":
        print("Error: This is not a git repository.")
        sys.exit(1)

    current_branch = run_command(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    if current_branch != "main":
        print(f"Error: You are not on the 'main' branch but on branch '{current_branch}'.")
        sys.exit(1)

    is_clean = run_command(['git', 'status', '--untracked-files=no', '--porcelain'])
    if is_clean != "":
        status = run_command(['git', 'status', '--untracked-files=no', '-s'])
        print(f"The working directory is not clean.\n"
               "You have the following unstaged or uncommitted changes:\n"
               "{status}")

# Run a shellcommand and return stdout
def run_command(argv):
    result = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8').stdout
    return result.strip()

# Ask the user for confirmation on whether to accept (y) or skip (s) the step or cancel (N) the playbook
def step(action, args):
    feedback = input(f"{action} [y/s/N] ")
    if feedback == "y":
        run_command(args)
    elif feedback == "s":
        print("Step skipped.")
        return
    else:
        print("Release playbook canceled.")
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
        print(f"You have more than two 'git remotes' specified, so guessing the correct one will most likely fail.\n"
               "Please use the --remote argument to set the correct one.\n"
               "{remotes}")

    for remote in remotes:
        remote_url = run_command(['git','remote','get-url',f'{remote}'])
        if search(origin, remote_url) is not None:
            return remote

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
    # TODO: Create a PR on GitHub automatically (since we know all the necessary infos) and paste a link to it in stdout
    print("Please use github to submit a pull-request against the main repository!")

def main():
    # Do some initial sanity checking of the repository and its state
    sanity_checks()

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

    print(f"Updating branch 'main' to avoid conflicts...")
    run_command(['git', 'pull'])

    # Run the release playbook
    release_playbook(args, repo)


if __name__ == "__main__":
    main()
