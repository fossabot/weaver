# vim:set ft=dockerfile:
FROM python:2.7-alpine
LABEL Description="Weaver" Vendor="CRIM" Maintainer="francis.charette-migneault@crim.ca"

# Configure hostname and ports for services
ENV HTTP_PORT 8080
ENV HTTPS_PORT 8443
ENV OUTPUT_PORT 8000
ENV HOSTNAME localhost
ENV WEAVER_URL weaver
# Set conda enviroment
ENV CONDA_HOME /opt/conda
ENV CONDA_ENV weaver
ENV CONDA_ENVS_DIR /opt/conda/envs
# Set current home
ENV HOME /root
# Start supervisor in foreground
ENV DAEMON_OPTS --nodaemon
WORKDIR /opt/birdhouse/src/weaver

# Ports used in birdhouse
EXPOSE 9001 $HTTP_PORT $HTTPS_PORT $OUTPUT_PORT

# Volume for data, cache, logfiles, configs
VOLUME /opt/birdhouse/var/lib
VOLUME /opt/birdhouse/var/log
VOLUME /opt/birdhouse/etc

# Create folders required for installation and fix permissions
RUN mkdir -p /opt/birdhouse/etc && \
    mkdir -p /opt/birdhouse/var/run && \
    mkdir -p /opt/birdhouse/var/tmp/nginx/client && \
    chmod 755 /opt/birdhouse/etc && \
    chmod 755 /opt/birdhouse/var/run

# Provide custom.cfg with settings for docker image
RUN printf "[buildout]\nextends=buildout.cfg profiles/docker.cfg" > custom.cfg

# Copy files for buildout setup and requirements
COPY Makefile buildout.cfg requirements*.txt ./
COPY profiles ./profiles/

# ====TMP
#RUN apk update && apk add make bash curl wget python-dev ca-certificates openssl
#RUN wget -q -O /etc/apk/keys/sgerrand.rsa.pub https://alpine-pkgs.sgerrand.com/sgerrand.rsa.pub
#RUN wget https://github.com/sgerrand/alpine-pkg-glibc/releases/download/2.29-r0/glibc-2.29-r0.apk
#RUN apk add glibc-2.29-r0.apk
#RUN mkdir -p /opt/birdhouse/src/weaver/downloads
#RUN python --version
#RUN curl https://repo.continuum.io/miniconda/Miniconda2-latest-Linux-x86_64.sh --silent --insecure --output /opt/birdhouse/src/weaver/downloads/Miniconda2-latest-Linux-x86_64.sh
#RUN mkdir -p ${CONDA_HOME}/pkgs
#RUN bash /opt/birdhouse/src/weaver/downloads/Miniconda2-latest-Linux-x86_64.sh -f -b -p ${CONDA_HOME}
#RUN make conda-env
# ====TMP

RUN apk update && \
    # install dependencies to run scripts
    apk add --no-cache make bash py-pip && \
    # install temporary build dependencies
    apk add --no-cache --virtual .build-deps gcc musl-dev python-dev wget curl ca-certificates openssl && \
    # install dependencies that allow to install conda on alpine with glibc
    # (see: https://github.com/sgerrand/alpine-pkg-glibc)
    wget -q -O /etc/apk/keys/sgerrand.rsa.pub https://alpine-pkgs.sgerrand.com/sgerrand.rsa.pub && \
    wget https://github.com/sgerrand/alpine-pkg-glibc/releases/download/2.29-r0/glibc-2.29-r0.apk && \
    apk add --no-cache glibc-2.29-r0.apk && \
    # install requirements, conda environment and buildout
    make bootstrap conda conda-env install && \
    # files generated by buildout are skipped in .dockerignore
    # files created from install process must be removed
    make clean-bld clean-cache clean-src && \
    apk --purge del .build-deps

# Copy application sources
COPY . /opt/birdhouse/src/weaver

# install without dependencies (pre-installed)
RUN make install-raw

CMD ["make", "online-update-config", "start"]
