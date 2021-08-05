#!/usr/bin/python3

#
# Write title and body of GitHub pull requests for a certain milestone to a markdown file
#

# Requires: pip install ghapi (https://ghapi.fast.ai/)
# Optional: A token to read from GitHub (there is a rate limit for
# anonymous API calls)


from ghapi.all import GhApi
import argparse
import os


def get_milestone(api, version):
    milestones = api.issues.list_milestones()
    for milestone in milestones:
        if version in milestone.title:
            print("%s (id %s)" % (milestone.title, milestone.number))
            return milestone.number


def get_pullrequest_infos(api, milestone, f):
    prs = api.pulls.list(state="closed")
    i = 0
    pr_count = 0

    while i <= (len(prs)):
        i += 1
        prs = api.pulls.list(state="closed", page=i)

        for pr in prs:
            if pr.milestone is not None and pr.milestone.number == milestone:
                pr_count += 1
                print("%s" % pr.url)
                f.write("  * %s: %s\n\n" % (pr.title, pr.body))

    return pr_count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version",
        help="Set the `version` variable",
        default="31")
    parser.add_argument(
        "--token",
        help="Supply a token for GitHub read access (optional)",
        default=None)
    args = parser.parse_args()

    repo = os.path.basename(os.getcwd())

    api = GhApi(repo=repo, owner='osbuild', token=args.token)

    milestone = get_milestone(api, args.version)

    filename = ("NEWS-%s.md" % args.version)
    if (os.path.isfile(filename)):
        print("Error: The file %s already exists." % filename)
    else:
        f = open(filename, "a")
        pr_count = get_pullrequest_infos(api, milestone, f)
        f.close()
        print("\nWritten %s PR summaries to %s" % (pr_count, filename))


if __name__ == "__main__":
    main()
