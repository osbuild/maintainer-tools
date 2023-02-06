# VM Helper

From Christian's repo https://github.com/gicmo/dot-devel/tree/master/vm-helper

## Spawn VMs

Handles the cloudinit parts and starts the VM using qemu.

## Configuration

No special configuration is needed compared to the original one.
But if you already do have a `~/.config/vmci` folder with the files `user-data` and `meta-data` configured the tool will take them.

You can force the overriding the values from you conf with the
`--override-user-data` option.

If no configuration is given, the tool will use by default the ssh key named
`id_rsa.pub` in your `~/.ssh` folder. You can specify another key to use with
the option `--ssh-key`.

The username and password configured by cloudinit are by default set to your
current username value for both your password and the username on the machine.
Root password is also set to your username.

You can change the default behavior with `--username` to set any username. And
`--password` to set a password that will be used for the user and the root
account.

# Generation

Comes along a new tool, "./gen" which is meant for requesting fresh images from
image-builder. To use it you need to have access to a valid offline token:
https://access.redhat.com/management/api

## options

### image

* `--distribution` the distribution you want
* `--architecture` same for the architecture
* `--packages` a list of packages, like 'git-all' or 'vim-common'
* `--activation-key` for rhel subscription
* `--organization` for rhel subscription

### Positional argument: command to run

#### Stage

Positional argument `stage` builds the image on stage. You need to provide
credentials to have access to stage and to be logged onto the VPN.

* `--username` is your ethel username
* `--password` is your ethel password
* `--password-command` is a command to invoke in order to retrieve the
  password. On my laptop it's set to `pass ethel_password`. https://wiki.archlinux.org/title/Pass
  is a nice tool, and I advice you find something that has an equivalent
  behavior, which is to return the token when prompted without any other values.

#### Prod

Positional argument `prod` builds the image on prod, you need to provide an
offline token to have access to prod.

* `--offline-token` provide the offline token on the command line, this is to be
  avoided, because you'll leak your token in your bashrc.
* `--offline-token-command` is a command to invoke in order to retrieve the
  token. On my laptop it's set to `pass offline_token`.

#### cache

The tool allow you to spawn a one time only disposable VM (default behavior) or
to keep your builds in the cache to use them later (more economical approach).

Objects in the cache are stored with a JSON file alongside them containing some
metadata. The date of creation, the request, the platform and the image name.

##### List

Positional argument `list` lists the entries in the cache. 

* `--clean` can be used to interactively be prompted to delete or keep a given
  cache entry.

### vm args

* you can specify any number of args for the `./vm` executable with `--vm-args`.
  You just have to put them in quotes.

# Example

```
./gen --name some_name --distribution rhel-91 --architecture x86_64 --packages
git-all vim-common --activation-key some_activation_key --organization 11224477
--vm-args "--memory 1014" stage --username some_login --password somepassword
```

This will build, store on cache and spawn the image.
You can the log onto it with `ssh localhost -p2222`
