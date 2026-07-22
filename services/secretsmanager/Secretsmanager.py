from services.Service import Service
from services.secretsmanager.drivers.SecretsmanagerSecret import SecretsmanagerSecret
from utils.Tools import _pi

class Secretsmanager(Service):
    def __init__(self, region):
        super().__init__(region)
        self.smClient = self.ssBoto.client('secretsmanager', config=self.bConfig)

    def advise(self):
        objs = {}
        paginator = self.smClient.get_paginator('list_secrets')
        for page in paginator.paginate():
            for secret in page.get('SecretList', []):
                name = secret.get('Name')
                _pi('SecretsManager::Secret', name)
                obj = SecretsmanagerSecret(secret, self.smClient)
                obj.run(self.__class__)
                objs['SecretsManager::' + name] = obj.getInfo()
                del obj
        return objs
