import botocore
from utils.Config import Config
from services.Service import Service
from services.ecr.drivers.EcrRepository import EcrRepository
from utils.Tools import _pi

class Ecr(Service):
    def __init__(self, region):
        super().__init__(region)
        ssBoto = self.ssBoto
        self.ecrClient = ssBoto.client('ecr', config=self.bConfig)

    def getRepositories(self):
        repos = []
        paginator = self.ecrClient.get_paginator('describe_repositories')
        for page in paginator.paginate():
            repos.extend(page.get('repositories', []))

        if not self.tags:
            return repos

        # Filter by tags if provided
        filtered = []
        for repo in repos:
            try:
                resp = self.ecrClient.list_tags_for_resource(resourceArn=repo['repositoryArn'])
                tags = [{'Key': t['Key'], 'Value': t['Value']} for t in resp.get('tags', [])]
                if self.resourceHasTags(tags):
                    filtered.append(repo)
            except botocore.exceptions.ClientError:
                filtered.append(repo)
        return filtered

    def advise(self):
        objs = {}
        repos = self.getRepositories()

        for repo in repos:
            name = repo.get('repositoryName')
            _pi('ECR::Repository', name)
            obj = EcrRepository(repo, self.ecrClient)
            obj.run(self.__class__)
            objs['ECR::' + name] = obj.getInfo()
            del obj

        return objs
