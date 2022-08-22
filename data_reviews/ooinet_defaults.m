% ooinet_defaults.m

BASE_URL = 'https://ooinet.oceanobservatories.org/api/m2m/';  % base M2M URL
ANNO_URL = '12580/anno/';                                     % Annotation Information
ASSET_URL = '12587/asset/';                                   % Asset and Calibration Information
DEPLOY_URL = '12587/events/deployment/inv/';                  % Deployment Information
SENSOR_URL = '12576/sensor/inv/';                             % Sensor Information
VOCAB_URL = '12586/vocab/inv/';                               % Vocabulary Information
STREAM_URL = '12575/stream/byname/';                          % Stream Information
PARAMETER_URL = '12575/parameter/';                           % Parameter Information

load('ooinet.credentials.mat')
