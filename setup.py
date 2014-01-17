from setuptools import setup, find_packages
import tord

classifiers = [
    'Development Status :: 4 - Beta',
    'Environment :: Web Environment',
    'Intended Audience :: Developers',
    'Intended Audience :: System Administrators',
    'License :: OSI Approved :: BSD License',
    'Operating System :: MacOS',
    'Operating System :: POSIX',
    'Operating System :: Unix',
    'Operating System :: Microsoft',
    'Operating System :: OS Independent',
    'Programming Language :: Python :: 2.7',
    'Topic :: Internet :: Proxy Servers',
    'Topic :: Internet :: WWW/HTTP :: HTTP Servers',
]

install_requires = open('requirements.txt', 'rb').read().strip().split()

setup(
    name                = 'tord',
    version             = tord.__version__,
    description         = tord.__description__,
    long_description    = open('README.md').read().strip(),
    author              = tord.__author__,
    author_email        = tord.__author_email__,
    url                 = tord.__homepage__,
    license             = tord.__license__,
    packages            = find_packages(),
    install_requires    = install_requires,
    classifiers         = classifiers
)
