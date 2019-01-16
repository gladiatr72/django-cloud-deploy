set -e
set -x
echo $PATH
wget https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-sdk-230.0.0-linux-x86_64.tar.gz -O ~/google-cloud-sdk.tar.gz
tar -xvzf ~/google-cloud-sdk.tar.gz -C ~/
source ~/google-cloud-sdk/install.sh
