# Copyright 2017 Open Source Robotics Foundation, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from superflore.utils import sanitize_string
from superflore.utils import download_yamls
from superflore.utils import get_license
from superflore.utils import resolve_dep
from superflore.utils import trim_string
from superflore.exceptions import UnknownLicense
from superflore.exceptions import UnresolvedDependency

from termcolor import colored
import yaml
import sys

class ebuild_keyword(object):
    def __init__(self, arch, stable):
        self.arch = arch
        self.stable = stable

    def to_string(self):
        if self.stable:
            return self.arch
        else:
            return '~{0}'.format(self.arch)


class Ebuild(object):
    """
    Basic definition of an ebuild.
    This is where any necessary variables will be filled.
    """
    def __init__(self):
        self.eapi = str(6)
        self.description = ""
        self.homepage = "https://wiki.ros.org"
        self.src_uri = None
        self.upstream_license = "LGPL-2"
        self.keys = list()
        self.rdepends = list()
        self.rdepends_external = list()
        self.depends = list()
        self.depends_external = list()
        self.distro = None
        self.cmake_package = True
        self.base_yml = None
        self.unresolved_deps = list()
        self.name = None
        self.has_patches = False
        self.die_msg = None
        self.python_3 = True
        self.illegal_desc_chars = '()[]{}|^$\\#\t\n\r\v\f\'\"\`'

    def add_build_depend(self, depend, internal=True):
        if depend in self.rdepends:
            return
        elif depend in self.rdepends_external:
            return
        elif internal:
            self.depends.append(depend)
        else:
            self.depends_external.append(depend)

    def add_run_depend(self, rdepend, internal=True):
        if internal:
            self.rdepends.append(rdepend)
        else:
            self.rdepends_external.append(rdepend)

    def add_keyword(self, keyword, stable=False):
        self.keys.append(ebuild_keyword(keyword, stable))

    def get_ebuild_text(self, distributor, license_text, die_msg=None):
        """
        Generate the ebuild in text, given the distributor line
        and the license text.

        @todo: make the year dynamic
        """
        ret = "# Copyright 2017 " + distributor + "\n"
        ret += "# Distributed under the terms of the " + license_text
        ret += " license\n\n"

        # EAPI=<eapi>
        ret += "EAPI=" + self.eapi + "\n"
        if self.python_3:
            ret += "PYTHON_COMPAT=( python{2_7,3_5} )\n\n"
        else:
            ret += "PYTHON_COMPAT=( python2_7 )\n\n"
        # inherits
        ret += "inherit ros-cmake\n\n"

        # description, homepage, src_uri
        py_ver = sys.version_info
        self.description =\
            sanitize_string(self.description, self.illegal_desc_chars)
        self.description = trim_string(self.description)
        if isinstance(self.description, str):
            ret += "DESCRIPTION=\"" + self.description + "\"\n"
        elif py_ver <= (3, 0) and isinstance(self.description, unicode):
            ret += "DESCRIPTION=\"" + self.description + "\"\n"
        else:
            ret += "DESCRIPTION=\"NONE\"\n"

        ret += "HOMEPAGE=\"" + self.homepage + "\"\n"
        ret += "SRC_URI=\"" + self.src_uri
        ret += " -> ${PN}-" + self.distro + "-release-${PV}.tar.gz\"\n\n"
        try:
            # license -- only add if valid
            if isinstance(self.upstream_license, str):
                split = self.upstream_license.split(',')
                if len(split) > 1:
                    # they did something like "BSD,GPL,blah"
                    ret += 'LICENSE="( '
                    for l in split:
                        l = get_license(l)
                        ret += '{0} '.format(l)
                    ret += ')"\n'
                else:
                    ret += "LICENSE=\""
                    ret += get_license(self.upstream_license) + "\"\n\n"
            elif py_ver < (3, 0) and isinstance(self.upstream_license, unicode):
                self.upstream_license = self.upstream_license.decode()
                split = self.upstream_license.split(',')
                if len(split) > 1:
                    # they did something like "BSD,GPL,blah"
                    ret += 'LICENSE="( '
                    for l in split:
                        l = get_license(l.replace(' ', ''))
                        ret += '{0} '.format(l)
                    ret += ')"\n'
                else:
                    ret += "LICENSE=\""
                    ret += get_license(self.upstream_license) + "\"\n\n"
            elif isinstance(self.upstream_license, list):
                ret += "LICENSE=\"( "
                for l in self.upstream_license:
                    l = get_license(l)
                    ret += '{0} '.format(l)
                ret += ")\"\n"
        except:
            pass
        # iterate through the keywords, adding to the KEYWORDS line.
        ret += "KEYWORDS=\""

        first = True
        for i in self.keys:
            if not first:
                ret += " "
            ret += i.to_string()
            first = False

        ret += "\"\n"
        # RDEPEND
        ret += "RDEPEND=\"\n"
        for rdep in sorted(self.rdepends):
            ret += "    " + "ros-" + self.distro + "/" + rdep + "\n"
        for rdep in sorted(self.rdepends_external):
            try:
                for res in resolve_dep(rdep, 'gentoo')[0]: 
                    ret += "    " + res + "\n"
            except UnresolvedDependency:
                self.unresolved_deps.append(rdep)

        ret += "\"\n"

        # DEPEND
        ret += "DEPEND=\"${RDEPEND}\n"
        for bdep in sorted(self.depends):
            ret += "    " + 'ros-{0}/{1}\n'.format(self.distro, bdep)
        for bdep in sorted(self.depends_external):
            try:
                for res in resolve_dep(bdep, 'gentoo')[0]:
                    ret += "    " + res + "\n"
            except UnresolvedDependency:
                self.unresolved_deps.append(bdep)
        ret += "\"\n\n"

        # SLOT
        ret += "SLOT=\"0\"\n"
        # CMAKE_BUILD_TYPE
        if self.name == "catkin":
            ret += "BUILD_BINARY=\"0\"\n"
        ret += "ROS_DISTRO=\"{0}\"\n".format(self.distro)
        ret += "ROS_PREFIX=\"opt/ros/${ROS_DISTRO}\"\n\n"

        # Patch source if needed.
        if self.has_patches:
            ret += "src_prepare() {\n"
            ret += "    cd ${P}\n"
            ret += "    EPATCH_SOURCE=\"${FILESDIR}\""
            ret += " EPATCH_SUFFIX=\"patch\" \\\n"
            ret += "    EPATCH_FORCE=\"yes\" epatch\n"
            ret += "    ros-cmake_src_prepare\n"
            ret += "}\n\n"

        special_pkgs = ['opencv3', 'stage']
        # source configuration
        if self.name in special_pkgs:
            ret += "src_configure() {\n"
            if self.name == 'opencv3':
                ret += "    filter-flags '-march=*' '-mcpu=*' '-mtune=*'\n"
            elif self.name == 'stage':
                ret += "    filter-flags '-std=*'\n"
            ret += "    ros-cmake_src_configure\n"
            ret += "}\n\n"

        if self.die_msg is not None:
            self.die_msg = ' {0}'.format(die_msg)
        else:
            self.die_msg = ''

        if len(self.unresolved_deps) > 0:
            raise UnresolvedDependency("failed to satisfy dependencies!")

        return ret.replace('    ', '\t')

    def get_unresolved(self):
        return self.unresolved_deps
