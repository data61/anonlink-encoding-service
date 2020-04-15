
# Installing the encoding service using helm

## Add the CSIRO's Data61 chart repo

    helm repo add data61 https://data61.github.io/charts

    helm repo update
    
Install the `encoding-service`:

    helm install data61/encoding-service [--namespace default] [--name encoding]

# Packaging a new release of the encoding service

    helm package encoding-service
    
Move the created file (e.g. `encoding-service-x.y.z.tgz`) to the [charts](https://github.com/data61/charts) 
repository in the `docs` folder. 
Follow the readme in the charts repository to update the index, commit and push.
