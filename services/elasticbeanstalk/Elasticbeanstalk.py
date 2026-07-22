import botocore
from services.Service import Service
from services.elasticbeanstalk.drivers.ElasticbeanstalkEnvironment import ElasticbeanstalkEnvironment
from utils.Tools import _pi

class Elasticbeanstalk(Service):
    def __init__(self, region):
        super().__init__(region)
        self.ebClient = self.ssBoto.client('elasticbeanstalk', config=self.bConfig)

    def advise(self):
        objs = {}
        paginator = self.ebClient.get_paginator('describe_environments')
        for page in paginator.paginate(IncludeDeleted=False):
            for env in page.get('Environments', []):
                name = env.get('EnvironmentName')
                _pi('ElasticBeanstalk::Environment', name)
                obj = ElasticbeanstalkEnvironment(env, self.ebClient)
                obj.run(self.__class__)
                objs['ElasticBeanstalk::' + name] = obj.getInfo()
                del obj
        return objs
