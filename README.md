[![Docker Repository on Quay](https://quay.io/repository/n1analytics/encoding-service/status "Docker Repository on Quay")](https://quay.io/repository/n1analytics/encoding-service)

# Encoding Service

## Set up

The Clkhash Service can be run in Docker. Ensure you have Docker and Docker Compose. To build the container, run:
```bash
$ ./build.sh
```

Then to run the service with Docker Compose:
```bash
$ docker-compose up
```

The address of the web server can be found with:
```bash
$ docker port clkhash-service_service_1 "8080"
```

## API

The API has a Swagger 2.0 specification in swagger.yaml. There is a Jupyter notebook with an example in docs/demo.ipynb.
