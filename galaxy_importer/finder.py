# (c) 2012-2019, Ansible by Red Hat
#
# This file is part of Ansible Galaxy
#
# Ansible Galaxy is free software: you can redistribute it and/or modify
# it under the terms of the Apache License as published by
# the Apache Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# Ansible Galaxy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# Apache License for more details.
#
# You should have received a copy of the Apache License
# along with Galaxy.  If not, see <http://www.apache.org/licenses/>.

import collections
import itertools
import json
import logging
import os

import attr

from subprocess import Popen
from subprocess import PIPE

from galaxy_importer import constants
from galaxy_importer.file_parser import ExtensionsFileParser
from galaxy_importer.galaxy_cli import GalaxyCLIWrapper


default_logger = logging.getLogger(__name__)

Result = collections.namedtuple("Result", ["content_type", "name", "path"])

ROLE_SUBDIRS = ["tasks", "vars", "handlers", "meta"]


class ContentFinder(object):
    """Searches for content in directories inside collection."""

    galaxy_cli = None

    '''
    def find_contents(self, path, logger=None):
        """Finds contents in path and return the results.

        :rtype: Iterator[Result]
        :return: Iterator of find results.
        """

        self.path = path
        self.log = logger or default_logger

        self.log.info("Finding content inside collection")
        contents = self._find_content()

        import epdb; epdb.st()

        try:
            first = next(contents)
        except StopIteration:
            return []
        else:
            return itertools.chain([first], contents)
    '''

    def find_contents(self, path, logger=None):
        """Finds contents in path and return the results.

        :rtype: Iterator[Result]
        :return: Iterator of find results.
        """
        self.path = path
        self.log = logger or default_logger

        self.galaxy_cli = GalaxyCLIWrapper(path=path, logger=logger)

        self.log.info("Finding content inside collection")
        contents = self._find_content()

        # import epdb; epdb.st()
        try:
            first = next(contents)
        except StopIteration:
            return []
        else:
            return itertools.chain([first], contents)

    '''
    def _find_content(self):
        for content_type, directory, func in self._content_type_dirs():
            content_path = os.path.join(self.path, directory)
            if not os.path.exists(content_path):
                continue
            yield from func(content_type, content_path)
    '''

    def _find_content(self):
        """Return an iterable of Result(s)."""

        '''
        content_type_map = {}
        for x in dir(constants.ContentType):
            y = x.lower().replace('_plugin', '')
            content_type_map[x] = y
        '''
        content_type_map = {}
        for plugin_type in constants.ANSIBLE_DOC_SUPPORTED_TYPES:
            print(plugin_type)
            content_type = constants.ContentType(plugin_type)
            content_type_map[content_type] = plugin_type
            print(f'\t{plugin_type} {content_type}')
        #import epdb; epdb.st()

        # Result(content_type=<ContentType.LOOKUP_PLUGIN: 'lookup'>, path='plugins/lookup/random_string.py')
        # Result(content_type=<ContentType.TEST_PLUGIN: 'test'>, path='plugins/test/fqdn_valid.py')
        old = []
        for content_type, directory, func in self._content_type_dirs():
            if content_type in content_type_map:
                continue
            # import epdb; epdb.st()
            content_path = os.path.join(self.path, directory)
            if not os.path.exists(content_path):
                continue
            for x in func(content_type, content_path):
                # old.append(x)
                yield x

        # this gets plugins but it doesn't get PLAYBOOKS/EDA/MODULE_UTILS/ etc ...
        new = []
        for plugin_type in constants.ANSIBLE_DOC_SUPPORTED_TYPES:
            ctype = constants.ContentType(plugin_type)
            plugins_docs = self.galaxy_cli.list_files(plugin_type)
            for key, path in plugins_docs.items():
                name = key[1].replace(self.galaxy_cli.fq_collection_name + '.', '')
                rel_path = path.replace(self.path + '/', '')
                yield Result(ctype, name, rel_path)

        #import epdb; epdb.st()

    def _find_plugins(self, content_type, content_dir):
        """Find all python files anywhere inside content_dir."""
        for path, _, files in os.walk(content_dir):
            for file in files:
                if not file.endswith(".py") or file == "__init__.py":
                    continue
                file_path = os.path.join(path, file)
                rel_path = os.path.relpath(file_path, self.path)
                base_name = os.path.basename(rel_path).rstrip('.py')
                yield Result(content_type, base_name, rel_path)

    def _find_roles(self, content_type, content_dir):
        """Find all dirs inside roles dir where contents match a role."""

        def is_dir_a_role(current_dir):
            """Check for contents indicating directory is a role."""
            _, dirs, _ = next(os.walk(current_dir))
            if set(ROLE_SUBDIRS) & set(dirs):
                return True
            return False

        def recurse_role_dir(path):
            """Iterate over all subdirs and yield roles."""
            if is_dir_a_role(path):
                rel_path = os.path.relpath(path, self.path)
                base_name = os.path.basename(rel_path)
                yield Result(content_type, base_name, rel_path)
                return
            path, dirs, _ = next(os.walk(path))
            for dir in dirs:
                yield from recurse_role_dir(os.path.join(path, dir))

        yield from recurse_role_dir(content_dir)

    def _content_type_dirs(self):
        for content_type in constants.ContentType:
            if content_type == constants.ContentType.ROLE:
                yield content_type, "roles", self._find_roles
            elif content_type == constants.ContentType.MODULE:
                yield content_type, "plugins/modules", self._find_plugins
            else:
                yield (
                    content_type,
                    "plugins/" + content_type.value,
                    self._find_plugins,
                )

        for content_type, full_path in self._get_ext_types_and_path():
            yield content_type, full_path, self._find_plugins

    def _get_ext_types_and_path(self):
        extension_dirs = ExtensionsFileParser(self.path).get_extension_dirs()

        if not extension_dirs:
            return []

        # remove ext_dir not currently allowed in the content list
        for ext_dir in list(extension_dirs):
            if ext_dir not in constants.ALLOWED_EXTENSION_DIRS:
                self.log.warning(
                    f"The extension type '{ext_dir}' listed in 'meta/extensions.yml' is "
                    "custom and will not be listed in Galaxy's contents nor documentation"
                )
                extension_dirs.remove(ext_dir)

        content_types_and_dirs = [
            (constants.ContentType(dir), f"extensions/{dir}") for dir in extension_dirs
        ]

        return content_types_and_dirs


@attr.s
class FileWalker(object):
    collection_path = attr.ib()
    file_errors = attr.ib(factory=list)

    def walk(self):
        full_collection_path = os.path.abspath(self.collection_path)

        for dirpath, dirnames, filenames in os.walk(
            full_collection_path, onerror=self.on_walk_error, followlinks=False
        ):
            for dirname in dirnames:
                dir_full_path = os.path.join(dirpath, dirname)
                yield dir_full_path

            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                yield full_path

    def on_walk_error(self, walk_error):
        default_logger.warning("walk error on %s: %s", walk_error.filename, walk_error)
        self.file_errors.append(walk_error)
