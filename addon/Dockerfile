ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-pip py3-pillow tzdata \
 && pip3 install --no-cache-dir --break-system-packages aiohttp

COPY app /opt/paperhub
COPY run.sh /run.sh
RUN chmod a+x /run.sh

WORKDIR /opt/paperhub
CMD ["/run.sh"]
