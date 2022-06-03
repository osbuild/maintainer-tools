Maintainer Tools
================

This repository hosts a collection of tools used by osbuild maintainers.

 - node_reservation.sh
 - update-distgit.sh

## `update-distgit.sh`

A useful script for updating osbuild packages downstream. When run in
a dist-git repository clone, it:
 - downloads upstream tarball
 - uploads it into the dist-git's look-aside cache
 - merges the new specfile from the tarball with the downstream changelog
 - makes a commit

A small example on how to rebase osbuild dist-git in Fedora to upstream
version 42:

```
~/maintainer-tools/update-distgit.py \
  --project osbuild \
  --version 42 \
  --author "Alice Bob <alicebob@example.com>" \
  --pkgtool fedpkg
```
