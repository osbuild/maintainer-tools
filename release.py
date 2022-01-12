#!/usr/bin/python3

"""Step interactively through the release process for osbuild"""

# Requires: pip install ghapi (https://ghapi.fast.ai/)

import argparse
import contextlib
import subprocess
import sys
import os
import getpass
import time
from datetime import date
import yaml
from ghapi.all import GhApi


class fg:  # pylint: disable=too-few-public-methods
    """Set of constants to print colored output in the terminal"""
    BOLD = '\033[1m'  # bold
    OK = '\033[32m'  # green
    INFO = '\033[33m'  # yellow
    ERROR = '\033[31m'  # red
    RESET = '\033[0m'  # reset


def msg_error(body):
    """Print error and exit"""
    print(f"{fg.ERROR}{fg.BOLD}Error:{fg.RESET} {body}")
    sys.exit(1)


def msg_info(body):
    """Print info message"""
    print(f"{fg.INFO}{fg.BOLD}Info:{fg.RESET} {body}")


def msg_ok(body):
    """Print ok status message"""
    print(f"{fg.OK}{fg.BOLD}OK:{fg.RESET} {body}")


def sanity_checks(repo):
    """Check if we are in a git repo, on the right branch and up-to-date"""
    if "osbuild" not in repo:
        msg_info("This script is only tested with 'osbuild' and 'osbuild-composer'.")

    is_git = run_command(['git', 'rev-parse', '--is-inside-work-tree'])
    if is_git != "true":
        msg_error("This is not a git repository.")

    current_branch = run_command(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    if "release" in current_branch:
        msg_info(f"You are already on a release branch: {current_branch}")
    elif "rhel-8" in current_branch:
        msg_info(f"You are going for a point release against: {current_branch}")
    elif current_branch != "main":
        msg_error(f"You are not on the 'main' branch but on branch '{current_branch}'.")

    is_clean = run_command(['git', 'status', '--untracked-files=no', '--porcelain'])
    if is_clean != "":
        status = run_command(['git', 'status', '--untracked-files=no', '-s'])
        msg_info("The working directory is not clean.\n"
                 "You have the following unstaged or uncommitted changes:\n"
                 f"{status}")
    has_gpg_key = run_command(['git', 'config', '--get', 'user.signingkey'])
    if has_gpg_key == "":
        msg_error("There is no GPG key set in your git configuration so you cannot create a signed tag.\n"
                  "If you already have a GPG key you can get the fingerprint with:\n"
                  "'gpg --list-secret-keys --keyid-format=long'\n"
                  "Please then set it using 'git config --global user.signingkey FINGERPRINT'")

    return current_branch


def run_command(argv):
    """Run a shellcommand and return stdout"""
    result = subprocess.run(  # pylint: disable=subprocess-run-check
        argv,
        capture_output=True,
        text=True,
        encoding='utf-8').stdout
    return result.strip()


def step(action, args, verify):
    """Ask the user whether to accept (y) or skip (s) the step or cancel (N) the playbook"""
    ret = None
    while ret is None:
        feedback = input(f"{fg.BOLD}Step: {fg.RESET}{action} ([y]es, [s]kip, [Q]uit) ").lower()
        if feedback == "y":
            if args is not None:
                out = run_command(args)
                if verify is not None:
                    out = run_command(verify)

                msg_ok(f"\n{out}")
            ret = "ok"
        elif feedback == "s":
            msg_info("Step skipped.")
            ret = "skipped"
        elif feedback in ("q", ""):
            msg_info("Release playbook quit.")
            sys.exit(0)

    return ret


def autoincrement_version(latest_tag):
    """Bump the version of the latest git tag by 1"""
    if latest_tag == "":
        msg_info("There are no tags yet in this repository.")
        version = "1"
    elif "." in latest_tag:
        version = latest_tag.replace("v", "").split(".")[0] + "." + str(int(latest_tag[-1]) + 1)
    else:
        version = int(latest_tag.replace("v", "")) + 1
    return version


def detect_github_token():
    """Check if a GitHub token is available"""
    token = os.getenv("GITHUB_TOKEN")
    if token:
        msg_info("Using token from '$GITHUB_TOKEN'")
        return token

    path = os.path.expanduser("~/.config/packit.yaml")
    with contextlib.suppress(FileNotFoundError, ImportError):
        with open(path, 'r', encoding='utf-8') as file:
            data = yaml.safe_load(file)
            token = data["authentication"]["github.com"]["token"]
            msg_info("Using token from '~/.config/packit.yaml'")
            return token

    return None


def list_prs_for_hash(args, api, repo, commit_hash):
    """Get pull request for a given commit hash"""
    query = f'{commit_hash} type:pr is:merged base:{args.base} repo:osbuild/{repo}'
    res = api.search.issues_and_pull_requests(q=query, per_page=20)
    if res is not None:
        items = res["items"]

        if len(items) == 1:
            ret = items[0]
        else:
            msg_info(f"There are {len(items)} pull requests associated with {commit_hash} - skipping...")
            for item in items:
                msg_info(f"{item.html_url}")
            ret = None
    else:
        ret = None

    return ret


def get_pullrequest_infos(args, repo, api, hashes):
    """Fetch the titles of all related pull requests"""
    summaries = []
    i = 0

    for commit_hash in hashes:
        i += 1
        print(f"Fetching PR {i}")
        time.sleep(2)
        pull_request = list_prs_for_hash(args, api, repo, commit_hash)
        if pull_request is not None:
            msg = f"  * {pull_request.title} (#{pull_request.number})"
        summaries.append(msg)

    summaries = list(dict.fromkeys(summaries))
    msg_ok(f"Collected summaries from {len(summaries)} pull requests ({i} commits).")
    return "\n".join(summaries)


def get_contributors(args):
    """Collect all contributors to a release based on the git history"""
    contributors = run_command(["git", "log", '--format="%an"', f"{args.latest_tag}..HEAD"])
    contributor_list = contributors.replace('"', '').split("\n")
    names = ""
    for name in sorted(set(contributor_list)):
        if name != "":
            names += f"{name}, "

    return names[:-2]


def create_release_tag(args, repo, api):
    """Create a release tag"""
    today = date.today()
    contributors = get_contributors(args)

    summaries = ""
    hashes = run_command(['git', 'log', '--format=%H', f'{args.latest_tag}..HEAD']).split("\n")
    msg_info(f"Found {len(hashes)} commits since {args.latest_tag} in {args.base}:")
    print("\n".join(hashes))
    summaries = get_pullrequest_infos(args, repo, api, hashes)

    message = (f"CHANGES WITH {args.version}:\n\n"
               f"----------------\n"
               f"{summaries}\n\n"
               f"Contributions from: {contributors}\n\n"
               f"— Location, {today.strftime('%Y-%m-%d')}")

    subprocess.call(['git', 'tag', '-s', '-e', '-m', message, f'v{args.version}', 'HEAD'])


def print_config(args, repo):
    """Print the values used for the release playbook"""
    print("\n--------------------------------\n"
          f"{fg.BOLD}Release:{fg.RESET}\n"
          f"  Component:     {repo}\n"
          f"  Version:       {args.version}\n"
          f"  Base branch:   {args.base}\n"
          f"{fg.BOLD}GitHub{fg.RESET}:\n"
          f"  User:          {args.user}\n"
          f"  Token:         {bool(args.token)}\n"
          f"--------------------------------\n")


def step_create_release_tag(args, repo, api):
    res = step("Create a tag for the release", None, None)
    if res != "skipped":
        create_release_tag(args, repo, api)

    step("Push the release tag upstream", ['git', 'push', 'origin', f'v{args.version}'], None)

def main():
    """Main function"""
    # Get some basic fallback/default values
    repo = os.path.basename(os.getcwd())
    current_branch = sanity_checks(repo)
    latest_tag = run_command(['git', 'describe', '--tags', '--abbrev=0'])
    version = autoincrement_version(latest_tag)
    username = getpass.getuser()
    token = detect_github_token()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--version",
                        help=f"Set the version for the release (Default: {version})",
                        default=version)
    parser.add_argument("-u", "--user", help=f"Set the username on GitHub (Default: {username})",
                        default=username)
    parser.add_argument("-t", "--token", help=f"Set the GitHub token (token found: {bool(token)})",
                        default=token)
    parser.add_argument(
        "-b", "--base",
        help=f"Set the base branch that the release targets (Default: {current_branch})",
        default=current_branch)

    args = parser.parse_args()

    args.latest_tag = latest_tag

    if args.token is None:
        msg_error("Please supply a valid GitHub token.")

    msg_info(f"Updating branch '{args.base}' to avoid conflicts...\n{run_command(['git', 'pull'])}")

    api = GhApi(repo=repo, owner='osbuild', token=args.token)

    print_config(args, repo)

    # Create a release tag
    step_create_release_tag(args, repo, api)


if __name__ == "__main__":
    main()
