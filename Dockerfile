FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple
ARG PIP_TRUSTED_HOST=mirrors.cloud.tencent.com
RUN pip install --no-cache-dir \
    -i "${PIP_INDEX_URL}" \
    --trusted-host "${PIP_TRUSTED_HOST}" \
    --disable-pip-version-check \
    -r requirements.txt

COPY app/ app/
COPY scripts/ scripts/
COPY questions/ questions/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV ROOT_PATH=/quiz
EXPOSE 8765

ENTRYPOINT ["/entrypoint.sh"]
