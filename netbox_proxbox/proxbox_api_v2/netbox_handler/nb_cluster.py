try:
    from virtualization.models import Cluster
except Exception as e:
    print(e)
    raise e

from .nb_cluster_type import upsert_cluster_type
from .nb_tag import tag


def upsert_cluster(proxmox_cluster):
    #
    # Cluster
    #

    proxmox_cluster_name = proxmox_cluster.name

    # Verify if there is any cluster created with:
    # Name equal to Proxmox's Cluster name
    # Cluster type equal to 'proxmox'
    cluster_proxbox = Cluster.objects.filter(name=proxmox_cluster_name).first()

    # If no 'cluster' found, create one using the name from Proxmox
    if cluster_proxbox is None:
        try:
            cluster_type_ = upsert_cluster_type()
            # Create the cluster with only name and cluster_type
            cluster = Cluster(
                name=proxmox_cluster_name,
                type_id=cluster_type_.id,
                type=cluster_type_,
            )
            cluster.save()
            tg = tag()
            cluster.tags.add(tg)
        except:
            return "Error creating the '{0}' cluster. Possible errors: the name '{0}' is already used.".format(
                proxmox_cluster_name)

    else:
        cluster = cluster_proxbox

    return cluster
