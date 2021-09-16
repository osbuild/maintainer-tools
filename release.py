#!/usr/bin/python3

"""Step interactively through the release process for osbuild"""

# Requires: pip install ghapi (https://ghapi.fast.ai/)

import argparse
import contextlib
import itertools
import subprocess
import sys
import os
import shutil
import getpass
from re import search, sub
from datetime import date
import yaml
import mistune
from ghapi.all import GhApi


class fg: #pylint: disable=too-few-public-methods
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
    return current_branch


def run_command(argv):
    """Run a shellcommand and return stdout"""
    result = subprocess.run( # pylint: disable=subprocess-run-check
        argv,
        capture_output=True,
        text=True,
        encoding='utf-8').stdout
    return result.strip()


def step(action, args, verify):
    """Ask the user whether to accept (y) or skip (s) the step or cancel (N) the playbook"""
    ret = None
    feedback = input(f"{fg.BOLD}Step: {fg.RESET}{action} [y/s/N] ")
    if feedback == "y":
        if args is not None:
            out = run_command(args)
            if verify is not None:
                out = run_command(verify)

            msg_ok(f"\n{out}")
    elif feedback == "s":
        msg_info("Step skipped.")
        ret = "skipped"
    else:
        msg_info("Release playbook canceled.")
        sys.exit(0)

    return ret


def autoincrement_version():
    """Bump the version of the latest git tag by 1"""
    latest_tag = run_command(['git', 'describe', '--abbrev=0'])
    if latest_tag == "":
        msg_info("There are no tags yet in this repository.")
        version = "1"
    elif "." in latest_tag:
        version = latest_tag.replace("v", "").split(".")[0] + "." + str(int(latest_tag[-1]) + 1)
    else:
        version = int(latest_tag.replace("v", "")) + 1
    return version


def guess_remote(repo, remotes):
    """Guess the git remote to push the release changes to"""
    origin = f"github.com[/:]osbuild/{repo}.git"

    if len(remotes) > 2:
        return None

    for remote in remotes:
        remote_url = run_command(['git', 'remote', 'get-url', f'{remote}'])
        if search(origin, remote_url) is None:
            return remote

    return None


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


def get_milestone(api, version):
    """Get the milestone id based on its version number"""
    milestones = api.issues.list_milestones()
    for milestone in milestones:
        if str(version) in milestone.title:
            msg_info(f"Gathering pull requests for milestone '{milestone.title}' ({milestone.url})")
            return milestone
    return None


def list_prs_for_milestone(api, milestone):
    """List all pull requests for a given milestone id"""
    query = f'milestone:"{milestone.title}" type:pr repo:osbuild/osbuild'
    count = 0

    for i in itertools.count():
        res = api.search.issues_and_pull_requests(q=query, per_page=20, page=i)
        items = res["items"]

        if not res:
            break

        for item in items:
            if item.state != "closed":
                continue
            yield item

        count += len(items)
        if count == res.total_count:
            break


def get_pullrequest_infos(api, milestone):
    """Fetch the summaries of the pull requests"""

    class NotesRenderer(mistune.Renderer):
        """Renderer for the release notes"""
        def __init__(self) -> None:
            super().__init__()
            self.in_notes = False

        def block_code(self, code, _lang): # pylint: disable=signature-differs
            if self.in_notes:
                self.in_notes = False
                return code
            return ""

        def paragraph(self, text):
            self.in_notes = "Release Notes" in text
            return ""

    summaries = []
    i = 0

    renderer = NotesRenderer()
    markdown = mistune.Markdown(renderer=renderer)

    for i, pull_request in enumerate(list_prs_for_milestone(api, milestone)):
        msg = markdown(pull_request.body)
        print(f" * {pull_request.url}")
        if not msg:
            msg = f"  * {pull_request.title}: {pull_request.body}"
        summaries.append(msg)

    msg_ok(f"Collected summaries from {i+1} pull requests.")
    return "\n\n".join(summaries)


def get_contributors():
    """Collect all contributors to a release based on the git history"""
    tag = run_command(['git', 'describe', '--abbrev=0'])
    contributors = run_command(["git", "log", '--format="%an"', f"{tag}..HEAD"])
    contributor_list = contributors.replace('"', '').split("\n")
    names = ""
    for name in sorted(set(contributor_list)):
        if name != "":
            names += f"{name}, "

    return names[:-2]


def get_unreleased(version):
    """Get all unreleased .md files and return their content"""
    summaries = ""
    path = f'docs/news/{version}'
    files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
    for file in files:
        with open(f'docs/news/{version}/{file}', 'r', encoding='utf-8') as markdown:
            lines = markdown.readlines()
            for line in lines:
                if "# " in line:
                    summaries += line.replace("# ", "  * ")

    return summaries


def update_news_osbuild(args, api):
    """Update the NEWS file for osbuild"""
    res = step(f"Update NEWS.md with pull request summaries for milestone {args.version}",
               None, None)
    if res == "skipped":
        return ""

    if args.token is None:
        msg_info("You have not passed a token so you may run into GitHub rate limiting.")

    summaries = ""
    milestone = get_milestone(api, args.version)
    if milestone is None:
        msg_info(f"Couldn't find a milestone for version {args.version}")
    else:
        summaries = get_pullrequest_infos(api, milestone)

    return summaries


def update_news_composer(args):
    """Update the NEWS file for osbuild-composer"""
    src = 'docs/news/unreleased/'
    target = f'docs/news/{args.version}'
    step(f"Create '{target}' for this release and move all unreleased .md files to it",
         ['mkdir', '-p', target], ['ls', '-d', target])
    files = os.listdir(src)
    for file in files:
        if file != ".gitkeep":
            shutil.move(os.path.join(src,file), target)
    msg_info(f"Content of docs/news/{args.version}:\n"
             "{run_command(['ls',f'docs/news/{args.version}'])}")

    step(f"Update NEWS.md with information from the markdown files in 'docs/news/{args.version}'",
         None, None)
    summaries = get_unreleased(args.version)
    return summaries


def update_news(args, repo, api):
    """Update the NEWS file"""
    today = date.today()
    contributors = get_contributors()

    if repo == "osbuild":
        summaries = update_news_osbuild(args, api)
    elif repo == "osbuild-composer":
        summaries = update_news_composer(args)

    filename = "NEWS.md"
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as file:
            content = file.read()

        with open(filename, 'w', encoding='utf-8') as file:
            file.write(f"## CHANGES WITH {args.version}:\n\n"
                       f"{summaries}\n"
                       f"Contributions from: {contributors}\n\n"
                       f"— Location, {today.strftime('%Y-%m-%d')}\n\n"
                       f"{content}")
    else:
        print(f"Error: The file {filename} does not exist.")


def bump_version(version, filename):
    """Bump the version in a file"""
    latest_tag = run_command(['git', 'describe', '--abbrev=0'])
    with open(filename, 'r', encoding='utf-8') as file:
        content = file.read()

    old_ver = latest_tag.replace("v", "")
    content = sub(f'(Version:\\s+){old_ver}\\b', f'\g<1>{str(version)}', content)

    with open(filename, 'w', encoding='utf-8') as file:
        file.write(content)


def create_pullrequest(args, api):
    """Create a pull request on GitHub from the fork to the main repository"""
    if args.user is None or args.token is None:
        msg_error("Missing credentials for GitHub.\n"
                  "       Without a token you cannot create a pull request.")

    if "release" in args.base:
        msg_info("You are probably re-executing this script, trying to create a pull request"
                 f"against a '{args.base}' (expected: 'main' or 'rhel-*').\n"
                 "       You may want to specifiy the base branch (--base) manually.")

    title = f'Prepare release {args.version}'
    head = f'{args.user}:release-{args.version}'
    body= 'Tasks:\n- [ ] Bump version\n- [ ] Update news'

    api.pulls.create(title, head, args.base, body, True, False, None)


def create_release(args, api):
    """Create a release on GitHub"""
    api.repos.create_release(f'v{args.version}', None, f'{args.version}',
                             f"## CHANGES WITH {args.version}", False, False, None)


def show_release_branches(args):
    """Check if a release branch already exists"""
    branches = run_command(['git','branch']).split()
    for branch in branches:
        if f"release-{args.version}" in branch:
            msg_error(f"The release branch 'release-{args.version}' already exists "
                      "but is not checked out.\n"
                      "       Consider deleting the branch if it's not clean or check it out.")


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
          f"  Remote:        {args.remote}\n"
           "--------------------------------\n")


def release_playbook(args, repo, api):
    """Execute all steps of the release playbook"""
    if "release" not in args.base:
        show_release_branches(args)
        step(f"Check out a new branch for the release {args.version}",
             ['git', 'checkout', '-b', f'release-{args.version}'],
             ['git','branch','--show-current'])

    res = step("Update the NEWS.md file", None, None)
    if res != "skipped":
        update_news(args, repo, api)

    res = step(f"Make the notes in NEWS.md release ready using {args.editor}", None, None)
    if res != "skipped":
        subprocess.call([f'{args.editor}', 'NEWS.md'])

    res = step(f"Bump the version where necessary ({repo}.spec, potentially setup.py)", None, None)
    if res != "skipped":
        bump_version(args.version, f"{repo}.spec")
        if repo == "osbuild":
            bump_version(args.version, "setup.py")

    print(f"{run_command(['git', 'diff'])}")
    step(f"Please review all changes {args.version}", None, None)

    if repo == "osbuild":
        step(f"Add and commit the release-relevant changes ({repo}.spec NEWS.md setup.py)",
             ['git', 'commit', f'{repo}.spec', 'NEWS.md', 'setup.py',
              '-s', '-m', f'{args.version}', '-m', f'Release osbuild {args.version}'], None)
    elif repo == "osbuild-composer":
        res = step(f"Add and commit the release-relevant changes ({repo}.spec NEWS.md setup.py)",
                   None, None)
        if res != "skipped":
            run_command(['git', 'add', 'docs/news'])
            run_command(['git', 'commit', f'{repo}.spec', 'NEWS.md',
                        'docs/news/unreleased', f'docs/news/{args.version}', '-s',
                        '-m', f'{args.version}', '-m', f'Release osbuild-composer {args.version}'])

    step(f"Push all release changes to the remote '{args.remote}'",
         ['git', 'push', '--set-upstream', f'{args.remote}', f'release-{args.version}'], None)

    res = step(f"Create a pull request on GitHub for user {args.user}", None, None)
    if res != "skipped":
        create_pullrequest(args, api)

    step("Has the upstream pull request been merged?", None, None)

    res = step("Switch back to the main branch from upstream and update it", None, None)
    if res != "skipped":
        run_command(['git','checkout',args.base])
        run_command(['git','pull'])
        msg_info(f"You are currently on branch: {run_command(['git','branch','--show-current'])}")

    step(f"Tag the release with version 'v{args.version}'",
         ['git', 'tag', '-s', '-m', f'{repo} {args.version}', f'v{args.version}', 'HEAD'],
         ['git','describe',f'v{args.version}'])

    step("Push the release tag upstream", ['git', 'push', f'v{args.version}'], None)

    res = step("Create the release on GitHub", None, None)
    if res != "skipped":
        create_release(args, api)

    step(f"Merge the pull request in Fedora: https://src.fedoraproject.org/rpms/{repo}/pull-requests",
         None, None)

    step("Get a Kerberos ticket for Fedora", ['kinit',f'{os.getenv("USER")}@FEDORAPROJECT.ORG'],
         ['klist'])

    step("Schedule a build with Koji", ['packit', 'build'], None)


def main():
    """Main function"""
    # Get some basic fallback/default values
    repo = os.path.basename(os.getcwd())
    current_branch = sanity_checks(repo)
    version = autoincrement_version()
    remotes = run_command(['git', 'remote']).split()
    remote = guess_remote(repo, remotes)
    username = getpass.getuser()
    token = detect_github_token()
    editor = os.getenv('EDITOR')

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--version",
                        help=f"Set the version for the release (Default: {version})",
                        default=version)
    parser.add_argument(
        "-r", "--remote",
        help=f"Set the git remote on GitHub to push the release changes to (Default: {remote})",
        default=remote)
    parser.add_argument("-u", "--user", help=f"Set the username on GitHub (Default: {username})",
                        default=username)
    parser.add_argument("-t", "--token", help=f"Set the GitHub token (token found: {bool(token)})",
                        default=token)
    parser.add_argument(
        "-e", "--editor",
        help=f"Set which editor shall be used to edit NEWS.md (Default: {editor})",
        default=editor)
    parser.add_argument(
        "-b", "--base",
        help=f"Set the base branch that the release targets (Default: {current_branch})",
        default=current_branch)
    args = parser.parse_args()

    if len(remotes) > 2 and args.remote is None:
        msg_error("You have more than two 'git remotes' specified, so guessing where to "
                  "create the pull request from would likely fail.\n"
                 f"       Please use the --remote argument to set the correct one: {remotes}")

    msg_info(f"Updating branch '{args.base}' to avoid conflicts...\n{run_command(['git', 'pull'])}")

    api = GhApi(repo=repo, owner='osbuild', token=args.token)

    print_config(args, repo)

    # Run the release playbook
    release_playbook(args, repo, api)


if __name__ == "__main__":
    main()
