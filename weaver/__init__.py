from pyramid.config import Configurator
import os
import sys
import logging
logging.captureWarnings(True)
LOGGER = logging.getLogger('weaver')

WEAVER_MODULE_DIR = os.path.abspath(os.path.dirname(__file__))
WEAVER_ROOT_DIR = os.path.abspath(os.path.dirname(WEAVER_MODULE_DIR))
sys.path.insert(0, WEAVER_ROOT_DIR)
sys.path.insert(0, WEAVER_MODULE_DIR)

# ===============================================================================================
#   DO NOT IMPORT ANYTHING NOT PROVIDED BY BASE PYTHON HERE TO AVOID 'setup.py' INSTALL FAILURE
# ===============================================================================================


def includeme(config):
    LOGGER.info("Adding weaver...")
    config.include('weaver.config')
    config.include('weaver.database')
    config.include('weaver.wps')
    config.include('weaver.wps_restapi')
    config.include('weaver.processes')
    config.include('weaver.tweens')


def main(global_config, **settings):
    """
    Creates a Pyramid WSGI application for Weaver.
    """
    from weaver.config import get_weaver_configuration
    from weaver.utils import parse_extra_options

    # validate and fix configuration
    weaver_config = get_weaver_configuration(settings)
    settings.update({'weaver.configuration': weaver_config})

    # Parse extra_options and add each of them in the settings dict
    settings.update(parse_extra_options(settings.get('weaver.extra_options', '')))

    local_config = Configurator(settings=settings)

    if global_config.get('__file__') is not None:
        local_config.include('pyramid_celery')
        local_config.configure_celery(global_config['__file__'])

    local_config.include('weaver')

    return local_config.make_wsgi_app()