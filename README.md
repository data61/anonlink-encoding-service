# Anonlink Encoding Service

## Set up

The Anonlink Encoding Service can be run in Docker. Ensure you have both Docker and Docker Compose 
installed. To build the container, run:
```bash
$ ./build.sh
```

Then to run the service with Docker Compose:
```bash
$ docker-compose up
```

The address of the web server can be found with:
```bash
$ docker-compose port encoding_app 8080
```

## API

The API is documented with a v3.0 OpenAPI specification. There is a Jupyter notebook with an example
in `docs/demo.ipynb`.
