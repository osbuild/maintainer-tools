###### Some notes & commands for beaker that I gathered

* You need to create an account by going to https://beaker.engineering.redhat.com/ with VPN on and kerberos ticket and just clicking login or something, it should be a  simple 1-click.
* If you plan to use the command-line, then you can install it according to  these instructions and it will work with kerberos also, https://docs.engineering.redhat.com/display/HTD/beaker.engineering.redhat.com+User+Guide#beaker.engineering.redhat.comUserGuide-Command-lineclient
* More help and docs on the website under Help (top right).

#### Commands 

- Reserve a machine (24-hours by default)

  `bkr workflow-simple --arch x86_64 --family=RedHatEnterpriseLinux9 --variant BaseOS --task=/distribution/check-install --task=/distribution/reservesys`

- Check the status of the last machine you reserved

  ``bkr job-results `bkr job-list --mine --unfinished --format=list -l 1` |  xmlstarlet fo 1>&2 | xmlstarlet sel -t -m "/job" -v '@status'``

- Get the hostname of the last machine you reserved

  ``bkr job-results `bkr job-list --mine --unfinished --format=list -l 1` |  xmlstarlet fo 1>&2 | xmlstarlet sel -t -m  "/job/recipeSet/recipe/roles/role/system" -v '@value'``

