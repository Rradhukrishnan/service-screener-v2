import traceback
import os
import boto3
import constants as _C

class Config:
    
    AWS_SDK = {
        'signature_version': 'v4'
    }

    ADVISOR = {
        'TITLE': 'Service Screener',
        'VERSION': '2.4.0',
        'LAST_UPDATE': '30-Jun-2025'
    }

    ADMINLTE = {
        'VERSION': '3.1.0',
        'DATERANGE': '2014-2021',
        'URL': 'https://adminlte.io',
        'TITLE': 'AdminLTE.io'
    }

    CURRENT_REGION = 'us-east-1'

    ## Services that are global, not region specific
    GLOBAL_SERVICES = [
        'iam',
        'cloudfront'
    ]
    
    ## Services with special keyword handling
    KEYWORD_SERVICES = [
        'lambda'    
    ]
    
    ## Define services supported for each Well-Architected Pillar
    PILLAR_SERVICES = {
        'security': [
            'iam', 'kms', 'cloudtrail', 'config', 'guardduty',
            'cloudwatch', 'waf', 'shield', 'inspector'
        ],
        'reliability': [
            'ec2', 's3', 'ebs', 'rds', 'autoscaling',
            'elasticloadbalancing', 'route53', 'backup'
        ],
        'cost_optimization': [
            'ec2', 'rds', 's3', 'elasticache', 'dynamodb',
            'lambda', 'cloudwatch', 'compute-optimizer'
        ]
    }

    ## Optional: Set default report structure or pillar list
    SUPPORTED_PILLARS = ['security', 'reliability', 'cost_optimization']

    @staticmethod
    def init():
        global cache
        cache = {}

    @staticmethod
    def setAccountInfo(__AWS_CONFIG):
        print(" -- Acquiring identify info...")
        
        ssBoto = Config.get('ssBoto', None)
        
        stsClient = ssBoto.client('sts')
        
        resp = stsClient.get_caller_identity()
        stsInfo = {
            'UserId': resp.get('UserId'),
            'Account': resp.get('Account'),
            'Arn': resp.get('Arn')
        }

        Config.set('stsInfo', stsInfo)
        acctId = stsInfo['Account']
        
        adir = 'adminlte/aws/' + acctId
        
        Config.set('HTML_ACCOUNT_FOLDER_FULLPATH', _C.ROOT_DIR + '/' + adir)
        Config.set('HTML_ACCOUNT_FOLDER_PATH', adir)

    @staticmethod 
    def set(key, val):
        cache[key] = val

    @staticmethod
    def get(key, defaultValue = False):
        DEBUG = False
        if key in cache:
            return cache[key]
        
        if defaultValue == False:
            if DEBUG:
                traceback.print_exc()
        
        return defaultValue
        
    @staticmethod
    def retrieveAllCache():
        return cache
        
    ## Get dynamic driver name for service classes
    @staticmethod
    def getDriversClassPrefix(driver):
        name = Config.extractDriversClassPrefix(driver)
        return 'regionInfo::' + name
    
    @staticmethod
    def extractDriversClassPrefix(driver):
        if driver[:2].lower() == 's3':
            return 's3'
            
        if driver[:7].lower() == 'elastic':
            classPrefix = driver[:10]
        else:
            classPrefix = driver[:3]
            if len(driver) > 3 and driver[:5] == 'cloud':
                classPrefix = driver[:8]
            
        return classPrefix
        

# Initialize config only once
try:
    if configHasInit:
        pass
except NameError:
    dashboard = {}
    Config.init()
    configHasInit = True

if __name__ == "__main__":
    print(os.getcwd())
