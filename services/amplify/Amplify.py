import botocore
from services.Service import Service
from services.amplify.drivers.AmplifyDriver import AmplifyDriver
from utils.Tools import _pi

class Amplify(Service):
    def __init__(self, region):
        super().__init__(region)
        ssBoto = self.ssBoto
        self.amplifyClient = ssBoto.client('amplify', config=self.bConfig)

    def getResources(self):
        results = []
        try:
            paginator = self.amplifyClient.get_paginator('list_apps')
            for page in paginator.paginate():
                results.extend(page.get('apps', []))
        except botocore.exceptions.ClientError as e:
            print(f'[Amplify] Error listing apps: {e.response["Error"]["Code"]}')
        return results

    def advise(self):
        objs = {}
        apps = self.getResources()
        for app in apps:
            app_name = app.get('name', app.get('appId', 'unknown'))
            _pi('Amplify', app_name)
            obj = AmplifyDriver(app, self.amplifyClient)
            obj.run(self.__class__)
            objs[f'Amplify::{app_name}'] = obj.getInfo()
            del obj
        return objs
