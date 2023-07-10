from dataclasses import dataclass, field

try:
    from virtualization.models import ClusterType
except Exception as e:
    print(e)
    raise e


def upsert_cluster_type(name=None, slug=None, description=None):
    name = name if name is not None else 'Proxmox'
    slug = slug if slug is not None else 'proxmox'
    description = description if description is not None else 'Proxmox Virtual Environment. Open-source server management platform'

    # Try to find the cluster with the name, slug
    cluster_type_proxbox = ClusterType.objects.get(name=name, slug=slug)

    # If no 'cluster_type' found, create one
    if cluster_type_proxbox is None:
        try:
            cluster_type = ClusterType(
                name=name,
                slug=slug,
                description=description
            )
        except Exception as request_error:
            raise RuntimeError(
                "Error creating the '{0}' cluster type.".format(name)) from request_error

    else:
        cluster_type = cluster_type_proxbox

    return cluster_type
