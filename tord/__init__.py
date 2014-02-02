from .tord import Application

VERSION = (0, 2, 1)
__version__ = '.'.join(map(str, VERSION[0:3])) + ''.join(VERSION[3:])
__description__ = 'Asynchronous websocket + pubsub based web framework'
__author__ = 'Abhinav Singh'
__author_email__ = 'mailsforabhinav@gmail.com'
__homepage__ = 'https://github.com/abhinavsingh/tord'
__license__ = 'BSD'