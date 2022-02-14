#!/bin/bash

# This script adds helper function to deploy a machine on AWS and install a dev
# environment for osbuild and osbuild-composer. It is a POC at the moment.
#
# Source this file in your bashrc to have access to the functions all the time
# note that you'll need to transfer the $AWS_INSTANCE_ID and $AWSHOST variables
# for the other terminal to access current reservation. For that use the function
# `node_print_reservation_infos`
#
# Prerequisites:
# you need to have configured AWS CLI on your computer
# you need to have a key to connect the instance, the script does not generate one
#
# What you can do with the script:
#
# node_reserve
#   Reserves a compute unit
#   Downloads the sources from github
#   Compile and installs the sources, at the end you have osbuild-composer
#       running and able to build images
#
# node_uploadiff
#   from a local github repo that is shared with the instance, make a patch and
#   apply it on the remote instance.
#
# node_open_tmux: opens a new tmux after the installation
#
# node_attach_tmux: attach to a tmux instance
#
# node_print_reservation_infos: print the IDs to export them on an other terminal
#
# node_terminate: terminate the reservation for current IDs
#
# Caveat: The script handle one reservation per terminal

# The type of machine you need
MACHINETYPE="t2.2xlarge"

# The ami ID
AMIID="ami-0efd1b90025adc1a0" # this one is a fedora 34
AMILOGIN="fedora"             # give the username associated with the AMI, it
                              # varies

# Defines the aws command
REGION="eu-central-1" #the region where to start the image
AWS_CMD="aws --region $REGION --color on ec2"

# The name of the credentials to access the instance
KEYNAME="tlavocat_keys"

# Private credentials location to connect to the instance
PEMLOCATION="$HOME/.ssh/tlavocat_keys.pem"

# A list of git remotes to pull from
# Use https remotes as the instance will not have access to your ssh key
# Also, the url is parsed to extract the name of the project to execute the
# corresponding installation script.
GITREMOTES=(
    "https://github.com/osbuild/osbuild-composer.git"
    "https://github.com/osbuild/osbuild.git"
    "https://github.com/osbuild/image-builder.git"
)

# For each remote, an execution script will be invoked. The name is in the form
# {project_name}_install.
#
# The first parameter to the function is a ssh command to the node on which
# execute the commands
# The second parameter is the name of the project that will be used to cd in it
# before executing the command

# install osbuild-composer
function osbuild-composer_install(){
    echo "cd $2 && sudo dnf -q builddep -y osbuild-composer.spec"
    $1 "cd $2 && sudo dnf -q builddep -y osbuild-composer.spec"
    _check_restult_terminate || return 1
    echo "cd $2 && make build"
    $1 "cd $2 && make build"
    _check_restult_terminate || return 1
    echo "cd $2 && sudo make install"
    $1 "cd $2 && sudo make install"
    _check_restult_terminate || return 1
    echo "cd $2 && sudo tools/gen-certs.sh \"\$(readlink -f test/data/x509/openssl.cnf)\" \"/etc/osbuild-composer\" \"/etc/osbuild-composer-test/ca\""
    $1 "cd $2 && sudo tools/gen-certs.sh \"\$(readlink -f test/data/x509/openssl.cnf)\" \"/etc/osbuild-composer\" \"/etc/osbuild-composer-test/ca\""
    _check_restult_terminate || return 1
    echo "cd $2 && sudo chmod 777 /etc/osbuild-composer/composer-key.pem"
    $1 "cd $2 && sudo chmod 777 /etc/osbuild-composer/composer-key.pem"
    _check_restult_terminate || return 1
    echo "cd $2 && sudo cp -fv test/data/composer/osbuild-composer.toml /etc/osbuild-composer/"
    $1 "cd $2 && sudo cp -fv test/data/composer/osbuild-composer.toml /etc/osbuild-composer/"
    _check_restult_terminate || return 1
    echo "cd $2 && sudo systemctl enable --now osbuild-composer-api.socket osbuild-worker@1.service"
    $1 "cd $2 && sudo systemctl enable --now osbuild-composer-api.socket osbuild-worker@1.service"
    _check_restult_terminate || return 1
}

# install osbuild
function osbuild_install(){
    echo "cd $2 && sudo pip3 install pytest"
    $1 "cd $2 && sudo pip3 install pytest"
    _check_restult_terminate || return 1
    echo "cd $2 && sudo pip3 install mako"
    $1 "cd $2 && sudo pip3 install mako"
    _check_restult_terminate || return 1
    echo "cd $2 && sudo dnf -q builddep -y osbuild.spec"
    $1 "cd $2 && sudo dnf -q builddep -y osbuild.spec"
    _check_restult_terminate || return 1
    echo "cd $2 && make rpm"
    $1 "cd $2 && make rpm"
    _check_restult_terminate || return 1
    echo "cd $2 && sudo dnf -q install -y ./rpmbuild/RPMS/noarch/*.rpm"
    $1 "cd $2 && sudo dnf -q install -y ./rpmbuild/RPMS/noarch/*.rpm"
    _check_restult_terminate || return 1
    $1 -tt 'bash -s' << EOF
#!/bin/bash

OSBUILD_LABEL=\$(matchpathcon -n /usr/bin/osbuild)

echo "osbuild label: \$OSBUILD_LABEL"
sudo chcon \$OSBUILD_LABEL /usr/bin/python3*
sudo chcon \$OSBUILD_LABEL \$(which pytest)

cd ~/osbuild

find . -maxdepth 2 -type f -executable -name 'org.osbuild.*' -print0 |
   while IFS= read -r -d '' module; do
   sudo chcon \${OSBUILD_LABEL} \${module}
done
EOF
}

# TODO install image-builder
function image-builder_install(){
    echo "cd $2 && echo \"placeholder\""
    $1 "cd $2 && echo \"placeholder\""
    _check_restult_terminate || return 1
}

# Colors, with helpers function to print things pretty
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color
BOLD='\033[1m' # No Color BOLD
function _boldecho(){
    echo -e "${BOLD}$1${NC}"
}
function _greenecho(){
    echo -e "${GREEN}$1${NC}"
}
function _redecho(){
    echo -e "${RED}$1${NC}"
}

function _yellowecho(){
    echo -e "${YELLOW}$1${NC}"
}

# Checks whether the previous command was a success and if it was not prints a
# red FAIL and invokes the node terminaison to free the ressource from aws
function _check_restult_terminate(){
    if [ $? -eq 0 ]; then
        _greenecho "Success"
    else
        _redecho "Previous command failed, terminating node"
        node_terminate
        return 1
    fi
}

# Checks whether the previous command was a success and if it was not prints a
# red FAIL and stops the script
function _check_restult(){
    if [ $? -eq 0 ]; then
        _greenecho "Success"
    else
        _redecho "Previous command failed"
        return 1
    fi
}

# write a warning in yellow
function _check_restult_warning(){
    if [ $? -eq 0 ]; then
        _greenecho "Success"
    else
        _yellowecho "Previous command failed"
    fi
}

# prompt an error and invite user to debug with the ssh command
function _check_restult_print_ssh(){
    if [ $? -eq 0 ]; then
        _greenecho "Success"
    else
        _redecho "Previous command failed, need debug"
        echo "$AWS_CMD terminate-instances --instance-ids $AWS_INSTANCE_ID" or node_terminate
        echo "ssh -oStrictHostKeyChecking=no -i $PEMLOCATION $AMILOGIN@$AWSHOST -t tmux"
        return 1
    fi
}

# Wait until ssh is up on the remote node
function _instanceWaitSSH() {
    local HOST="$1"
    for LOOP_COUNTER in {0..30}; do
        if ssh-keyscan "$HOST" > /dev/null 2>&1; then
            _greenecho "SSH is up!"
            break
        elif (($LOOP_COUNTER == 29)); then
            _redecho "SSH is not up... termintating"
            return 1
        else
            _yellowecho "Retrying in 5 seconds... $LOOP_COUNTER"
            sleep 5
        fi
    done
}

function node_reserve(){
    # Reserve an instance with a root disk of 30GB
    _boldecho "Reserving an instance"
    export AWS_INSTANCE_ID=$(jq -r '.Instances[].InstanceId' \
        <($AWS_CMD run-instances \
        --key-name "$KEYNAME" \
        --image-id $AMIID \
        --count 1 \
        --instance-type $MACHINETYPE \
        --block-device-mappings \
        '{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":30}}' \
        --user-data file://<(cat <<EOF
#!/bin/bash
iptables -F
service sshd restart
EOF
            ) \
        --security-group-ids sg-08a1ec985f7f58d6e \
        ) \
    )
    _greenecho "The instance is reserved $AWS_INSTANCE_ID"
    _boldecho "Wait for running state"
    $AWS_CMD wait instance-running --instance-ids $AWS_INSTANCE_ID
    _greenecho "$The Instance $AWS_INSTANCE_ID is running"

    # get the hostname
    _boldecho "Get the host's ip"
    export AWSHOST=$(jq -r '.Reservations[].Instances[].PublicIpAddress' \
        <( \
        $AWS_CMD describe-instances --instance-ids "$AWS_INSTANCE_ID" \
        ) \
    )
    _greenecho "Instance's IP $AWSHOST"
    _boldecho "Wait for ssh to be up"
    _instanceWaitSSH "$AWSHOST" || return 1

    # Check access with ssh
    _boldecho Check access with ssh
    ssh -oStrictHostKeyChecking=no -i $PEMLOCATION $AMILOGIN@$AWSHOST -t echo "OK" &>/dev/null
    _check_restult_terminate || return 1

    # Install first packages
    _boldecho "Performing base package installation"
    ssh -oStrictHostKeyChecking=no -i $PEMLOCATION $AMILOGIN@$AWSHOST -t \
        sudo dnf -q -y install htop \
        skopeo \
        tmux \
        make \
        git \
        go \
        ranger \
        openssl \
        rpm-build \
        aws \
        qemu \
        setools-console \
        setroubleshoot \
        container-selinux \
        lvm2
    _check_restult_terminate || return 1

    # Install the sources
    _boldecho "Cloning git repos and installing"
    for t in ${GITREMOTES[@]}; do
        _boldecho "Cloning git $t"
        ssh -oStrictHostKeyChecking=no -i $PEMLOCATION $AMILOGIN@$AWSHOST -t git clone $t
        _check_restult_terminate || return 1
        IFS='/' read -r -a split <<< "$t"
        IFS='.' read -r -a split <<< ${split[-1]}
        _boldecho "perform install for ${split}[0]"
        ${split[0]}_install "ssh -oStrictHostKeyChecking=no -i $PEMLOCATION $AMILOGIN@$AWSHOST -t" ${split[0]} || return 1
    done

    # Append helper commands in bash_history to have them on ctrl+r
    ssh -oStrictHostKeyChecking=no -i $PEMLOCATION $AMILOGIN@$AWSHOST -t " echo \"journalctl -f -u osbuild-worker@1.service\" >> ~/.bash_history"
    ssh -oStrictHostKeyChecking=no -i $PEMLOCATION $AMILOGIN@$AWSHOST -t " echo \"journalctl -f -u osbuild-composer.service\" >> ~/.bash_history"
    ssh -oStrictHostKeyChecking=no -i $PEMLOCATION $AMILOGIN@$AWSHOST -t " echo \"make build; sudo systemctl disable --now osbuild-composer.service osbuild-composer-api.socket osbuild-worker@1.service && sudo make install && sudo systemctl enable --now osbuild-composer-api.socket osbuild-worker@1.service\" >> ~/.bash_history"

    # Print a reminder to connect and terminate the instance
    _greenecho "Installation done on $AWSHOST. To terminate instance later enter the command below"
    echo "$AWS_CMD terminate-instances --instance-ids $AWS_INSTANCE_ID"
    _boldecho "Start working on your instance"
    echo "ssh -oStrictHostKeyChecking=no -i $PEMLOCATION $AMILOGIN@$AWSHOST -t tmux"
}

#
# This function upload the current state of the local repo as a patch on the
# remote machine.
#
# First, the hash of the top commit is fetched on the remote.
# Second, the patch between this hash and local state is produced
# Third, the patch is applied
#
# The remote machine will be deployed with an up-to-date origin/main, then if
# your local state is behind what's on the repo, you will be prompt to update
# your code base. (Because the commit on the remote does not exit on your local
# machine, then, you can't produce a patch !)
function node_uploadiff(){
    ssh_base="ssh -q -oStrictHostKeyChecking=no -i $PEMLOCATION $AMILOGIN@$AWSHOST -t"
    # get the project name we are in
    git status &> /dev/null
    if [ $? -gt 0 ]; then
        _redecho "Are you in a git folder ?"
        return 1
    fi
    local project=$(git config --local remote.origin.url|sed -n 's#.*/\([^.]*\)\.git#\1#p')

    # get the remote commit hash
    local remote_hash=$($ssh_base "cd $project && git rev-parse HEAD")
    remote_hash=${remote_hash/$'\r'/}
    if [ $? -gt 0 ]; then
        _redecho "There is an error, maybe you are in the wrong git on the local machine ?"
        return 1
    fi
    # check that the hash is in the project
    git show "${remote_hash}" &>/dev/null
    if [ $? -gt 0 ]; then
        _redecho "remote hash for  ${project}: ${remote_hash}"
        _redecho "Update your local project, remote commit does not exist there"
        return 1
    fi
    # store the patch
    git diff --binary ${remote_hash} > /tmp/patchforremote
    if [ $? -gt 0 ]; then
        _redecho "can't produce patch"
        return 1
    fi

    # reset hard remote
    $ssh_base "cd $project && git reset --hard ${remote_hash}" &> /dev/null
    if [ $? -gt 0 ]; then
        _redecho "can't reset remote"
        return 1
    fi

    # clean
    $ssh_base "cd $project && git clean -f -d" &> /dev/null
    if [ $? -gt 0 ]; then
        _redecho "can't clean remote"
        return 1
    fi

    # send the patch to the remote
    rsync -e "ssh -i ${PEMLOCATION}" -aAX /tmp/patchforremote $AMILOGIN@${AWSHOST}:/tmp/patchforremote
    $ssh_base "cd $project && git apply /tmp/patchforremote"
    if [ $? -gt 0 ]; then
        _redecho "can't apply patch"
        return 1
    fi
    _greenecho "patch applied on remote"
}

function node_print_reservation_infos(){
    _boldecho "reservation details"
    echo "ID $AWS_INSTANCE_ID"
    echo "IP $AWSHOST"
    SCRIPTPATH="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
    _boldecho "to have access to the commands from another terminal:"
    echo "export AWS_INSTANCE_ID=$AWS_INSTANCE_ID; export AWSHOST=$AWSHOST"
}

function node_open_tmux(){
    ssh -oStrictHostKeyChecking=no -i $PEMLOCATION $AMILOGIN@$AWSHOST -t tmux
}

function node_attach_tmux(){
    ssh -oStrictHostKeyChecking=no -i $PEMLOCATION $AMILOGIN@$AWSHOST -t tmux attach
}

function node_terminate(){
    echo "Terminate instance $AWS_INSTANCE_ID"
    $AWS_CMD terminate-instances --instance-ids $AWS_INSTANCE_ID
    _check_restult || return 1
}
