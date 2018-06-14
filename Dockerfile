FROM alpine:3.7
MAINTAINER Jakub Nabaglo "jakub.nabaglo@data61.csiro.au"

COPY clkhash_service.py clkhash_worker.py database.py swagger.yaml requirements.txt /clkhash-service/
WORKDIR /clkhash-service

RUN apk add --no-cache python3 libpq \
    && apk add --no-cache --virtual .build-deps g++ python3-dev postgresql-dev libffi-dev \
    && pip3 install --upgrade pip \
    && pip3 install --upgrade -r requirements.txt \
    && apk del --no-cache .build-deps \
    && rm -fr /tmp/* /var/cache/apk/* /root/.cache/pip

RUN adduser -D -H -h /var/www user \
    && chown user:user /clkhash-service
USER user
