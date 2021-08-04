#!/usr/bin/python3

#
# Step interactively through the release process for osbuild
#

import argparse
import subprocess, sys
import os


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
    else:
        print(f"Updating '{current_branch}' to avoid conflicts...")

    is_clean = run_command(['git', 'status', '--untracked-files=no', '--porcelain'])
    if is_clean != "":
        status = run_command(['git', 'status', '--untracked-files=no', '-s'])
        print(f"The working directory is not clean.\n"
               "You have the following unstaged or uncommitted changes:\n"
               "{status}")
    else:
        run_command(['git', 'pull'])

# Run a shellcommand and return stdout
def run_command(argv):
    result = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8').stdout
    return result.strip()

# Ask the user for confirmation on whether to continue
def step(action, args):
    # TODO: Consider adding a third state (skip?) so the playbook can be easily restarted
    feedback = input(f"{action} [y/N] ")
    if feedback == "y":
        run_command(args)
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
    origin = f"github.com/osbuild/{repo}.git"
    remotes = run_command(['git','remote']).split("\n")
    if len(remotes) > 2:
        print(f"You have more than two 'git remotes' specified, so guessing the correct one will most likely fail.\n"
               "Please use the --remote argument to set the correct one.\n"
               "{remotes}")

    for remote in remotes:
        remote_url = run_command(['git','remote','get-url',f'{remote}'])
        if remote_url.__contains__(origin) == False:
            return remote

# Execute all steps of the release playbook
def release_playbook(version, remote, repo):
    step(f"Check out a new branch for the release {version}", ['git', 'checkout', '-b', f'release-{version}'])
    step("Generate template for new release", ['make', 'release'])
    step(f"Bump the version to {version}", ['make', 'bump-version'])
    step(f"Please make sure the version was bumped correctly to {version}", ['git', 'diff'])
    # TODO: Call the pr_summaries.py script for osbuild or assemble the news from docs/news/unreleased for composer
    step(f"Add and commit the release-relevant changes ({repo}.spec NEWS.md setup.py)",
          ['git', 'commit', f'{repo}.spec', 'NEWS.md', 'setup.py', '-s', f'-m {version}', f'-m "Release osbuild {version}"'])
    step(f"Push all release changes to the remote '{remote}'",
          ['git', 'push', '--set-upstream', f'{remote}', f'release-{version}'])
    # TODO: Create a PR on GitHub automatically (since we know all the necessary infos) and paste a link to it in stdout
    print("Please use github to submit a pull-request against the main repository!")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", help="Set the `version` for the release")
    parser.add_argument("--remote", help="Set the `remote` on github to push the release changes to")
    args = parser.parse_args()

    # Do some initial sanity checking of the repository and its state
    sanity_checks()

    # Determine the version for the release
    if (args.version is None):
        version = autoincrement_version()
    else:
        version = args.version
    
    # Determine the remote to push the release to
    repo = os.path.basename(os.getcwd())
    if (args.remote is None):
        remote = guess_remote(repo)
    else:
        remote = args.remote

    # Run the release playbook
    release_playbook(version, remote, repo)


if __name__ == "__main__":
    main()
