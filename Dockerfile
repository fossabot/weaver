# vim:set ft=dockerfile:
FROM birdhouse/bird-base:latest
MAINTAINER https://github.com/bird-house/twitcher

LABEL Description="twitcher application" Vendor="Birdhouse"

# Configure hostname and ports for services
ENV HTTP_PORT 8080
ENV HTTPS_PORT 8443
ENV OUTPUT_PORT 8000
ENV HOSTNAME localhost

ENV POSTGRES_USER user
ENV POSTGRES_PASSWORD password
ENV POSTGRES_HOST postgres
ENV POSTGRES_DB default
ENV POSTGRES_PORT 5432
ENV MAGPIE_URL magpie
ENV TWITCHER_URL twitcher
ENV MAGPIE_SECRET to_be_override
ENV TWITCHER_PROTECTED_PATH /ows/proxy
ENV TWITCHER_WPS_RESTAPI_PATH /

# Set current home
ENV HOME /root

# cd into application
WORKDIR /opt/birdhouse/src/twitcher

# Provide custom.cfg with settings for docker image
RUN printf "[buildout]\nextends=buildout.cfg profiles/docker.cfg" > custom.cfg

# Set conda enviroment
ENV ANACONDA_HOME /opt/conda
ENV CONDA_ENV twitcher
ENV CONDA_ENVS_DIR /opt/conda/envs

COPY Makefile requirements.sh bootstrap.sh ./

# Install system dependencies and Anaconda
RUN make sysinstall anaconda

# Copy files for buildout setup and requirements
COPY buildout.cfg environment.yml requirements.txt ./
COPY profiles ./profiles/

# setup Anaconda environment and setup buildout
# baseinstall runs `pip install -r requirements.txt
RUN make bootstrap baseinstall

# Running make clean is not required
# files generated by buildout are skipped in .dockerignore

# Volume for data, cache, logfiles, ...
VOLUME /opt/birdhouse/var/lib
VOLUME /opt/birdhouse/var/log

# Volume for configs
VOLUME /opt/birdhouse/etc

# Ports used in birdhouse
EXPOSE 9001 $HTTP_PORT $HTTPS_PORT $OUTPUT_PORT

# Start supervisor in foreground
ENV DAEMON_OPTS --nodaemon

# Copy application sources
COPY . /opt/birdhouse/src/twitcher

# Create folders required for installation
RUN mkdir -p /opt/birdhouse/etc && mkdir -p /opt/birdhouse/var/run

    # `make install` command without its Makefile dependencies
RUN . $ANACONDA_HOME/bin/activate $CONDA_ENV && \
    bin/buildout buildout:anaconda-home=$ANACONDA_HOME -c custom.cfg && \
    # fix permissions for birdhouse folders
    chmod 755 /opt/birdhouse/etc && \
    chmod 755 /opt/birdhouse/var/run && \
    # install the package in place,
    # without installing any dependencies (they were previously installed)
    pip install -e . --no-deps

RUN mkdir -p /opt/birdhouse/var/tmp/nginx/client
CMD ["make", "online-update-config", "start"]
