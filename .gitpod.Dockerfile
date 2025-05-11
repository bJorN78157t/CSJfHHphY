FROM gitpod/workspace-full

USER gitpod

RUN curl -fsSL https://deno.land/x/install/install.sh | sh && \
  echo "# Deno" >> ~/.bash_profile && \
  echo 'export DENO_INSTALL="/home/gitpod/.deno"' >> ~/.bash_profile && \
  echo 'export PATH="$DENO_INSTALL/bin:$PATH"' >> ~/.bash_profile

# Install custom tools, runtime, etc. using apt-get
# For example, the command below would install "bastet" - a command line tetris clone:
#
# RUN sudo apt-get -q update && \
#     sudo apt-get install -yq bastet && \
#     sudo rm -rf /var/lib/apt/lists/*
#
# More information: https://www.gitpod.io/docs/config-docker/
