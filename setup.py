#!/usr/bin/env python
#  -*- coding: utf-8 -*-

"""Setup for asyncio-cmdline."""

import errno
import re
import subprocess

from ast import literal_eval
from os import chdir
from os.path import dirname
from setuptools import setup, find_packages


def get_version(filename='version.py'):
    """Build version number from git repository tag."""

    try:
        f = open(filename, 'r')

    except IOError as e:
        if e.errno != errno.ENOENT:
            raise

        m = None

    else:
        m = re.match(r'^\s*__version__\s*=\s*(?P<version>.*)$', f.read(), re.M)
        f.close()

    __version__ = literal_eval(m.group('version')) if m else None

    try:
        git_version = subprocess.check_output(['git',
                                               'describe',
                                               '--dirty',
                                               '--tags',
                                               '--long',
                                               '--always']).decode()

    except subprocess.CalledProcessError:
        if __version__ is None:
            raise ValueError("cannot determine version number")

        return __version__

    m = re.match(r'^\s*'
                 r'(?P<version>\S+?)'
                 r'(-(?P<post>\d+)-(?P<commit>g[0-9a-f]+))?'
                 r'(-(?P<dirty>dirty))?'
                 r'\s*$', git_version)
    if not m:
        raise ValueError("cannot parse git describe output")

    git_version = m.group('version')
    post = m.group('post')
    commit = m.group('commit')
    dirty = m.group('dirty')

    local = []

    if post and int(post) != 0:
        git_version += '.post%d' % (int(post),)
        if commit:
            local.append(commit)

    if dirty:
        local.append(dirty)

    if local:
        git_version += '+' + '.'.join(local)

    if git_version != __version__:
        with open(filename, 'w') as f:
            f.write("__version__ = %r\n" % (git_version,))

    return git_version


def get_long_description(filename='README.md'):
    """Convert description to reStructuredText format."""

    try:
        with open(filename, 'r') as f:
            description = f.read()

    except OSError as e:
        if e.errno != errno.ENOENT:
            raise

        return None

    try:
        process = subprocess.Popen([
                'pandoc',
                '-f', 'markdown_github',
                '-t', 'rst',
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            universal_newlines=True,
            )

    except OSError as e:
        if e.errno == errno.ENOENT:
            return None

        raise

    description, __ = process.communicate(input=description)

    if process.poll() is None:
        process.kill()
        raise Exception("pandoc did not terminate")

    if process.poll():
        raise Exception("pandoc terminated abnormally")

    return description


if __name__ == '__main__':
    chdir(dirname(__file__))
    setup(
            name='asyncio-cmdline',
            version=get_version(),
            author='Niels Boehm',
            author_email='blubberdiblub@gmail.com',
            description="Command Line input/output compatible with asyncio.",
            long_description=get_long_description(),
            license='MIT',
            keywords=[
                'command line',
                'input',
                'output',
                'terminal',
            ],
            url='https://github.com/blubberdiblub/asyncio-cmdline/',
            install_requires=[
                'blessed',
            ],
            # extras_require={
            #     },
            test_suite='tests',
            packages=find_packages(exclude=[
                'tests',
                'tests.*',
                '*.tests',
                '*.tests.*',
            ]),
            include_package_data=True,
            zip_safe=False,
            # entry_points={
            #     'console_scripts': [
            #     ],
            # },
            classifiers=[
                'Development Status :: 2 - Pre-Alpha',
                'Environment :: Console',
                'Framework :: AsyncIO',
                'Intended Audience :: Developers',
                'License :: OSI Approved :: MIT License',
                'Operating System :: POSIX :: Linux',
                'Programming Language :: Python',
                'Programming Language :: Python :: 3',
                'Programming Language :: Python :: 3.4',
                'Programming Language :: Python :: 3.5',
                'Programming Language :: Python :: 3.6',
                'Programming Language :: Python :: 3.7',
                'Topic :: Software Development :: Libraries',
                'Topic :: Software Development :: Libraries :: Python Modules',
                'Topic :: Software Development :: User Interfaces',
            ],
        )
