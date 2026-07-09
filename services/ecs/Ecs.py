import botocore
from utils.Config import Config
from services.Service import Service
from services.ecs.drivers.EcsCluster import EcsCluster
from utils.Tools import _pi

class Ecs(Service):
    def __init__(self, region):
        super().__init__(region)
        ssBoto = self.ssBoto
        self.ecsClient = ssBoto.client('ecs', config=self.bConfig)

    def getClusters(self):
        clusters = []
        paginator = self.ecsClient.get_paginator('list_clusters')
        for page in paginator.paginate():
            clusters.extend(page.get('clusterArns', []))
        return clusters

    def advise(self):
        objs = {}
        clusterArns = self.getClusters()

        if not clusterArns:
            return objs

        # Describe all clusters in one call (max 100)
        resp = self.ecsClient.describe_clusters(
            clusters=clusterArns,
            include=['SETTINGS', 'STATISTICS', 'TAGS']
        )

        for cluster in resp.get('clusters', []):
            name = cluster.get('clusterName', cluster.get('clusterArn'))
            _pi('ECS::Cluster', name)
            obj = EcsCluster(cluster, self.ecsClient)
            obj.run(self.__class__)
            objs['ECS::' + name] = obj.getInfo()
            del obj

        return objs
