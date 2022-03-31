#!/bin/bash

# This script can be used to perform manual cleanup of any orphaned
# Gitlab CI runners. It's meant to be run manually from the executor.
# The script checks for each job folder that has a terraform lock file
# in it and if it's older than $HOURS_BACK it runs terraform destroy
# and removes the folder + ssh key from known_hosts


# Look only for JOBS that have a terraform lock file in them
TF_FILES=$(find . -iname ".terraform.lock.hcl")
# Anything older than 5 hours should have timed out and be destroyed
HOURS_BACK=5
TIME_TO_DELETE=$(date -d "- $HOURS_BACK hours" +%s)

for FILE  in $TF_FILES; do
    RUNNER_FOLDER=$(echo "$FILE" | sed -r 's/(\/.terraform.lock.hcl)//')
    JOB_FOLDER=$(echo "$FILE" | grep -Eo '.\/[0-9]*\/')
    MODIFIED_TIME=$(stat "$RUNNER_FOLDER" --format %Y)
    if [[ $MODIFIED_TIME < $TIME_TO_DELETE ]];then
        VM_IP=$(jq -r .outputs.ip_address.value[0] terraform.tfstate)
        pushd "$RUNNER_FOLDER" || exit
        terraform destroy -auto-approve
        popd || exit
        ssh-keygen -R "$VM_IP"
        rm -rf "$JOB_FOLDER"
    fi
done
