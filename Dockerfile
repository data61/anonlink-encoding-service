ARG VERSION=6fc6226b427c7361e073894ed56450dfea8ec89bec4d4e869c5702bcab5d5cae
FROM data61/anonlink-base:${VERSION}
MAINTAINER Anonlink Developers "anonlink@googlegroups.com"

COPY requirements.txt /var/www/
USER root
RUN pip install --upgrade -r requirements.txt

COPY clkhash_service.py clkhash_worker.py database.py openapi.yaml requirements.txt /var/www/

RUN chown user:user /var/www
USER user

WORKDIR /var/www
