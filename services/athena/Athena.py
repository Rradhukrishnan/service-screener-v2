import botocore
from services.Service import Service
from services.athena.drivers.AthenaWorkgroup import AthenaWorkgroup
from utils.Tools import _pi

class Athena(Service):
    def __init__(self, region):
        super().__init__(region)
        self.athenaClient = self.ssBoto.client('athena', config=self.bConfig)

    def advise(self):
        objs = {}
        paginator = self.athenaClient.get_paginator('list_work_groups')
        for page in paginator.paginate():
            for wg in page.get('WorkGroups', []):
                name = wg.get('Name')
                if name == 'primary':
                    # Still check primary workgroup
                    pass
                _pi('Athena::WorkGroup', name)
                try:
                    detail = self.athenaClient.get_work_group(WorkGroup=name)
                    obj = AthenaWorkgroup(detail.get('WorkGroup', {}), self.athenaClient)
                    obj.run(self.__class__)
                    objs['Athena::' + name] = obj.getInfo()
                    del obj
                except botocore.exceptions.ClientError as e:
                    print(f"  [WARN] Could not get workgroup {name}: {str(e)}")
        return objs
