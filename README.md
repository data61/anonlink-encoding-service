# clkhash-service

A simple REST api for [clkhash](https://github.com/n1analytics/clkhash)

This proposal is to include a simple REST server (e.g. written in flask) and wrap it in a docker 
image so that clkhash can easily used by other languages and systems.

The server would simply provide a REST interface to hash PII data into CLKs. Because hashing can
take a non trivial amount of time it probably makes sense to have an async api. This also allows
for an incremental updates api - to come in a later version.

Initial API:

### Add a new linkage project
```
POST /api/projects
{
  "name": "my first set of hashes"
  "schema": "TODO - WIP schema design...",
  "keys": ["secret 1", "secret 2"] 
}

{
  "id": "someprojectid"
}
```

### Hash a bunch of PII

```
POST /api/projects/{someprojectid}
{
  "data": [
    {"a feature label": "some feature observation", "email": "blah@example.com", ....}, 
    {...},
  ]
}

{
  "status": "hashing",
  "entities uploaded": 10000
  "entities hashed": 0
}
```


### Get hashing progress

```
GET /api/projects/{someprojectid}
{
  "status": "hashing",
  "entities uploaded": 10000
  "entities hashed": 0
}
```

### Get hash results

```
GET /api/projects/{someprojectid}/clks
{
  "clks": [
    "Lots of base64 encoded CLKs....", ...
  ]
}
```

### Delete Project

```
DELETE /api/projects/{someprojectid}
```

Possibly delete pii or clks?
```
DELETE /api/projects/{someprojectid}/clks
```

# Running

$ pip install -r requirements.txt
$ FLASK_APP=server.py flask run


Basic test

    python example_usage.py
    
    