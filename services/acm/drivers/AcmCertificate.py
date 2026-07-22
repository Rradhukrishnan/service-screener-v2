from datetime import datetime, timezone
from services.Evaluator import Evaluator

class AcmCertificate(Evaluator):
    def __init__(self, cert):
        super().__init__()
        self.cert = cert
        self._resourceName = cert.get('CertificateArn', 'unknown')
        self.init()

    def _checkExpiry30Days(self):
        expiry = self.cert.get('NotAfter')
        if expiry:
            days = (expiry - datetime.now(timezone.utc)).days
            if days <= 7:
                self.results['ACMCertExpiring7Days'] = [-1, f'Expires in {days} days']
            elif days <= 30:
                self.results['ACMCertExpiring30Days'] = [-1, f'Expires in {days} days']

    def _checkStatus(self):
        status = self.cert.get('Status')
        if status == 'EXPIRED':
            self.results['ACMCertExpired'] = [-1, self.cert.get('DomainName')]
        elif status == 'VALIDATION_TIMED_OUT':
            self.results['ACMCertValidationFailed'] = [-1, self.cert.get('DomainName')]

    def _checkWildcard(self):
        domain = self.cert.get('DomainName', '')
        if domain.startswith('*.'):
            self.results['ACMWildcardCertificate'] = [0, domain]

    def _checkInUse(self):
        in_use = self.cert.get('InUseBy', [])
        if not in_use:
            self.results['ACMCertNotInUse'] = [0, self.cert.get('DomainName')]

    def _checkTransparencyLogging(self):
        opts = self.cert.get('Options', {})
        if opts.get('CertificateTransparencyLoggingPreference') == 'DISABLED':
            self.results['ACMTransparencyLoggingDisabled'] = [-1, self.cert.get('DomainName')]
