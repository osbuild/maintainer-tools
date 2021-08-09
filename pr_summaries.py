#!/usr/bin/python3

#
# Write title and body of GitHub pull requests for a certain milestone to a markdown file
#

# Requires: pip install ghapi (https://ghapi.fast.ai/)
# Optional: A token to read from GitHub (there is a rate limit for
# anonymous API calls)


import argparse
import os
import sys
from datetime import date
import subprocess
from ghapi.all import GhApi


def get_milestone(api, version):
    milestones = api.issues.list_milestones()
    for milestone in milestones:
        if version in milestone.title:
            print(f"Gathering pull requests for milestone '{milestone.title}' ({milestone.url})")
            return milestone.number
    return None


def get_pullrequest_infos(api, milestone):
    prs = api.pulls.list(state="closed")
    i = 0
    pr_count = 0
    summaries = ""

    while i <= (len(prs)):
        i += 1
        prs = api.pulls.list(state="closed", page=i)

        for pr in prs:
            if pr.milestone is not None and pr.milestone.number == milestone:
                pr_count += 1
                print(f" * {pr.url}")
                summaries += f"  * {pr.title}: {pr.body}\n\n"

    print(f"Collected summaries from {pr_count} pull requests.")
    return summaries


def get_contributors(version):
    contributors = subprocess.run(["git", "log", '--format="%an"', f"v{str(int(version) - 1)}..HEAD"],
                                  capture_output=True,
                                  text=True,
                                  check=True,
                                  encoding='utf-8').stdout
    contributor_list = contributors.replace('"', '').split("\n")
    names = ""
    for name in set(sorted(contributor_list)):
        if name != "":
            names += f"{name}, "
    return names[:-2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", help="Set the version for the release")
    parser.add_argument("--token", help="Supply a token for GitHub read access (optional)", default=None)
    args = parser.parse_args()

    if token is None:
        print("Warning: You have not passed a token so you may run into GitHub rate limiting.")
    api = GhApi(repo="osbuild", owner='osbuild', token=args.token)

    milestone = get_milestone(api, args.version)
    if milestone is None:
        print(f"Error: Couldn't find a milestone for version {args.version}")
        sys.exit(1)

    filename = "NEWS.md"
    if (os.path.exists(filename)):
        with open(filename, 'r') as file:
            content = file.read()

        summaries = get_pullrequest_infos(api, milestone)
        today = date.today()
        contributors = get_contributors(args.version)

        with open(filename, 'w') as file:
            file.write(f"## CHANGES WITH {args.version}:\n\n"
                       f"{summaries}"
                       f"Contributions from: {contributors}\n\n"
                       f"— Location, {today.strftime('%Y-%m-%d')}\n\n"
                       f"{content}")
    else:
        print(f"Error: The file {filename} does not exist.")


if __name__ == "__main__":
    main()
