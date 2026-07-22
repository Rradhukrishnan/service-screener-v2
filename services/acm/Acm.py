from services.Service import Service
from services.acm.drivers.AcmCertificate import AcmCertificate
from utils.Tools import _pi

class Acm(Service):
    def __init__(self, region):
        super().__init__(region)
        self.acmClient = self.ssBoto.client('acm', config=self.bConfig)

    def advise(self):
        objs = {}
        paginator = self.acmClient.get_paginator('list_certificates')
        for page in paginator.paginate(CertificateStatuses=['ISSUED', 'EXPIRED', 'VALIDATION_TIMED_OUT', 'PENDING_VALIDATION']):
            for cert in page.get('CertificateSummaryList', []):
                arn = cert.get('CertificateArn')
                _pi('ACM::Certificate', arn.split('/')[-1])
                detail = self.acmClient.describe_certificate(CertificateArn=arn)
                obj = AcmCertificate(detail.get('Certificate', {}))
                obj.run(self.__class__)
                objs['ACM::' + arn.split('/')[-1]] = obj.getInfo()
                del obj
        return objs
