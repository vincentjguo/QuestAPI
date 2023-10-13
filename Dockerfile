# syntax=docker/dockerfile:1

# Comments are provided throughout this file to help you get started.
# If you need more help, visit the Dockerfile reference guide at
# https://docs.docker.com/engine/reference/builder/

FROM selenium/standalone-edge:latest as base

USER root

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

RUN apt update -y && apt install -y libssl-dev openssl build-essential zlib1g-dev

RUN wget https://www.python.org/ftp/python/3.12.0/Python-3.12.0.tgz && \
    tar xzvf Python-3.12.0.tgz && cd Python-3.12.0 && ./configure && \
    make && make install

RUN apt install -y pip

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

# Create a non-privileged user that the app will run under.
# See https://docs.docker.com/develop/develop-images/dockerfile_best-practices/#user
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    appuser

# Download dependencies as a separate step to take advantage of Docker's caching.
# Leverage a cache mount to /root/.cache/pip to speed up subsequent builds.
# Leverage a bind mount to requirements.txt to avoid having to copy them into
# into this layer.
RUN python3.12 pip install --upgrade pip && \
    python3.12 pip install --no-cache-dir --upgrade -r /code/requirements.txt


# Switch to the non-privileged user to run the application.
USER appuser

# Copy the source code into the container.
COPY ./api /code/api

# Expose the port that the application listens on.
EXPOSE 4444

# Run the application.
CMD ["uvicorn", "api.main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "4444"]
